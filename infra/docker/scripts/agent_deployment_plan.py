"""Plan and execute explicitly staged Worker batches from an operator workstation."""
import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from uuid import UUID


@dataclass(frozen=True)
class WorkerStage:
    service: str
    revision: UUID
    artifact_digest: str


@dataclass(frozen=True)
class ComposeDeploymentPlan:
    project: str
    operation_id: UUID
    workers: tuple[WorkerStage, ...]

    def validate_plan(self):
        if not re.fullmatch(r'shenzhi-(phase3[12]|staging)-[a-z0-9][a-z0-9-]{2,39}', self.project):
            raise ValueError('an explicit isolated Compose project is required')
        services = {worker.service for worker in self.workers}
        if not 1 <= len(self.workers) <= 50 or len(services) != len(self.workers):
            raise ValueError('one to fifty distinct Worker services required')
        for worker in self.workers:
            if not re.fullmatch(r'agent-worker-[a-z0-9][a-z0-9-]{0,32}', worker.service):
                raise ValueError('only dedicated Worker services are supported')
            if not re.fullmatch(r'sha256:[a-f0-9]{64}', worker.artifact_digest):
                raise ValueError('immutable artifact digest required')

    def prepare(self):
        self.validate_plan()
        return {'operation_id': str(self.operation_id), 'mode': 'dry_run',
                'workers': [{'service': item.service, 'revision': str(item.revision),
                             'artifact_digest': item.artifact_digest} for item in self.workers]}

    def deploy_batch(self):
        self.validate_plan()
        return ['docker', 'compose', '-p', self.project, 'up', '-d', '--no-deps', '--no-build', '--pull', 'never',
                *(worker.service for worker in self.workers)]

    def get_status(self):
        self.validate_plan()
        return ['docker', 'compose', '-p', self.project, 'ps', '--format', 'json',
                *(worker.service for worker in self.workers)]

    def reconcile(self):
        return {'operation_id': str(self.operation_id), 'action': 'verify_fresh_worker_manifests'}

    def pause(self):
        return {'operation_id': str(self.operation_id), 'action': 'pause_in_admin'}

    def rollback(self, known_good):
        return ComposeDeploymentPlan(self.project, self.operation_id, known_good).prepare()


def compose_config(file, plan):
    endpoint = subprocess.run(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'],
                              capture_output=True, text=True, timeout=8, check=True).stdout.strip()
    if not endpoint.startswith(('unix://', 'npipe://')):
        raise ValueError('a local Docker context is required')
    base = ['docker', 'compose', '-f', str(file), '-p', plan.project]
    result = subprocess.run([*base, 'config', '--format', 'json'], capture_output=True, text=True, timeout=12, check=True)
    return base, json.loads(result.stdout)


def verify_stage(root, config, worker, operation):
    service = config['services'][worker.service]
    if not re.fullmatch(r'[^\s]+@sha256:[a-f0-9]{64}', service.get('image', '')):
        raise ValueError('Worker image must use a content digest')
    if any(service.get(key) for key in ('privileged', 'devices', 'ports', 'pid', 'ipc', 'network_mode', 'cap_add')):
        raise ValueError('Worker exceeds the isolated deployment boundary')
    environment = service.get('environment', {})
    labels = service.get('labels', {})
    if labels.get('org.shenzhi.operation-id') != str(operation):
        raise ValueError('Worker is not staged for this operation')
    if any(environment.get(key) for key in ('AGENT_CONFIG_MANAGEMENT_TOKEN', 'AGENT_CONFIG_VALIDATOR_SECRET', 'AGENT_MANAGEMENT_TOKEN')):
        raise ValueError('management credentials must be absent from Worker')
    mount_path = environment.get('AGENT_EXECUTION_CONFIG_FILE')
    artifact = None
    for mount in service.get('volumes', []):
        if mount.get('type') == 'volume':
            source = config.get('volumes', {}).get(mount.get('source'), {})
            if source.get('external') or source.get('driver_opts') or not source.get('name', '').startswith(config['name'] + '_'):
                raise ValueError('Worker volume must belong to the isolated project')
            continue
        source = Path(mount.get('source', '')).resolve()
        if mount.get('type') != 'bind' or not mount.get('read_only') or not source.is_relative_to(root):
            raise ValueError('Worker bind mounts must be read-only and within the Compose directory')
        if mount_path and mount.get('target') == mount_path:
            artifact = source
    if artifact is None:
        raise ValueError('Worker artifact must be mounted by exact path')
    with artifact.open('rb') as stream:
        content = stream.read(524_289)
    if len(content) > 524_288:
        raise ValueError('Worker artifact is too large')
    spec = json.loads(content)
    if (spec.get('revision_id'), spec.get('config_digest')) != (str(worker.revision), worker.artifact_digest):
        raise ValueError('Worker artifact differs from the deployment plan')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compose_file', type=Path)
    parser.add_argument('plan_file', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        document = json.loads(args.plan_file.read_text(encoding='utf-8'))
        plan = ComposeDeploymentPlan(document['project'], UUID(document['operation_id']), tuple(
            WorkerStage(item['service'], UUID(item['revision']), item['artifact_digest']) for item in document['workers']
        ))
        plan.validate_plan()
        if args.apply:
            import os
            if os.environ.get('DOCKER_HOST') or os.environ.get('DOCKER_CONTEXT'):
                raise ValueError('use the configured local Docker context')
            file = args.compose_file.resolve(strict=True)
            base, configuration = compose_config(file, plan)
            for worker in plan.workers:
                verify_stage(file.parent, configuration, worker, plan.operation_id)
            result = subprocess.run([*base, *plan.deploy_batch()[4:]], capture_output=True, timeout=60)
            print(json.dumps({'operation_id': str(plan.operation_id),
                              'state': 'awaiting_worker_confirmation' if result.returncode == 0 else 'pending_reconcile'}))
            return result.returncode
        print(json.dumps(plan.prepare()))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        print(json.dumps({'state': 'pending_reconcile' if args.apply else 'invalid_plan'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
