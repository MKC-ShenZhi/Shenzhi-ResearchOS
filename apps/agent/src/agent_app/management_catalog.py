"""Read-only projections of the Agent API process configuration."""
import os
from urllib.parse import urlsplit

from agent_contracts.canonical import digest, request_digest_v1
from agent_contracts.management import Document, Evidence, Model, Provider, Resource, Skill, States, Tool

from agent_app.capabilities.ask_user import ask_user_tool
from agent_app.capabilities.chart_tools import chart_tool, image_search_tool
from agent_app.capabilities.fetch_url import fetch_url_tool
from agent_app.capabilities.knowledge import knowledge_tools
from agent_app.capabilities.read_paper import read_paper_tool
from agent_app.capabilities.web_search import web_search_tool
from agent_app.control.metering import GateDenied, now_utc
from agent_app.errors import BusinessError
from agent_app.execution.metering import controlled_resource_digest, model_identity, tool_identity
from agent_app.extensions.skills import default_store, read_skill_tool
from agent_app.extensions.skills import _parse_frontmatter
from agent_app.extensions.workspace import WORKSPACE_ROOT, Workspace, build_workspace_tools
from agent_app.integrations.llm.registry import ResolvedModel
from agent_app.integrations.llm.resolver import load_registry


def observed(state, source, *, config_revision=None):
    return Evidence(state=state, source=source, observed_at=now_utc(), config_revision=config_revision)


def llm_catalog():
    registry = load_registry()
    revision = os.getenv('AGENT_MODEL_ROUTE_REVISION', '').strip()[:255] or None
    defaults = {}
    for purpose in ('chat', 'agent'):
        try:
            defaults[purpose] = registry.default_model(purpose).id
        except BusinessError:
            continue
    providers = {}
    for provider_id, provider in registry.providers.items():
        url = urlsplit(provider.spec.base_url)
        # Leave out endpoint paths, queries and credentials.
        host = url.hostname
        origin = f'{url.scheme}://{url.netloc}' if host else None
        providers[provider_id] = Provider(
            provider_id=provider_id, protocol=provider.spec.protocol, base_url=origin,
            credential_present=bool(provider.key.get_secret_value()), enabled=provider.spec.enabled,
            model_ids=sorted(m.id for m in registry.models.values() if m.provider_id == provider_id),
            states=States(registered=observed('yes', 'api_registry'),
                          loaded=observed('yes', 'api_registry'),
                          configured=observed('yes' if provider.configured else 'no', 'api_registry')),
        )
    models = {}
    for model_id, spec in registry.models.items():
        version = None
        try:
            definition = ResolvedModel(spec, registry.providers[spec.provider_id])
            version = digest(model_identity(definition).model_dump(mode='json'))
        except BusinessError:
            pass
        configured = registry.providers[spec.provider_id].configured and spec.enabled
        models[model_id] = Model(
            model_id=model_id, provider_id=spec.provider_id, upstream_model_id=spec.upstream_model,
            label=spec.label, brand=spec.brand, capabilities=spec.capabilities.model_dump(),
            default_purposes=[purpose for purpose, default in defaults.items() if default == model_id],
            enabled=spec.enabled, config_revision=revision, capability_version=version,
            states=States(registered=observed('yes', 'api_registry', config_revision=revision),
                          loaded=observed('yes', 'api_registry', config_revision=revision),
                          configured=observed('yes' if configured else 'no', 'api_registry', config_revision=revision)),
        )
    return providers, models


def tool_catalog():
    # Factories define ToolSpecs without running tools or creating a Runtime.
    groups = [
        ('core', [], [web_search_tool(), read_paper_tool(), fetch_url_tool()]),
        ('knowledge', [], knowledge_tools()),
        ('core', ['non_fast'], [ask_user_tool()]),
        ('workspace', ['non_fast', 'workspace_or_session'],
         [chart_tool(workspace_root=None), image_search_tool(workspace_root=None)]),
    ]
    store = default_store()
    if store.names():
        groups.append(('skill', ['nonempty_skill_store'], [read_skill_tool(store)]))
    if WORKSPACE_ROOT.is_dir():
        groups.append(('workspace', ['workspace_or_session'],
                       build_workspace_tools(Workspace(WORKSPACE_ROOT), allow_shell=False)))
    tools = {}
    for source, conditions, specs in groups:
        for tool in specs:
            spec = tool.spec
            tool_id = 'tool:' + spec.name
            required = conditions or (['non_fast'] if spec.name == 'citation_graph' else [])
            try:
                version = digest(tool_identity(tool).model_dump(mode='json'))
            except BusinessError:
                version = None
            tools[tool_id] = Tool(
                tool_id=tool_id, name=spec.name, description=spec.description, source=source,
                parameters_schema=spec.parameters, schema_digest=request_digest_v1(spec.parameters),
                capability_version=version, conditions=required,
                registration='conditional' if required else 'base',
                states=States(registered=observed('yes', 'api_tool_factory')),
            )
    return tools


def skill_catalog():
    store = default_store()
    return {name: skill_summary(store.get(name)) for name in store.names()}


def skill_summary(skill):
    resources = []
    metadata = None
    integrity = 'unknown'
    try:
        integrity = 'yes' if controlled_resource_digest(skill.root) == skill.resource_content_digest else 'no'
        if integrity == 'yes':
            metadata, _ = _parse_frontmatter(skill.path.read_text(encoding='utf-8'))
            for folder, kind in [('references', 'reference'), ('scripts', 'script')]:
                for path in sorted((skill.root / folder).rglob('*')):
                    if path.is_file() and len(resources) < 100:
                        resources.append(Resource(name=path.relative_to(skill.root).as_posix(),
                                                  kind=kind, size=path.stat().st_size))
    except (OSError, ValueError):
        integrity = 'no'
    return Skill(
        name=skill.name, description=skill.description[:1024],
        source='unknown' if os.getenv('AGENT_EXECUTION_CONFIG_FILE') else 'builtin' if skill.executable else 'vendor',
        configuration_source='immutable_artifact' if os.getenv('AGENT_EXECUTION_CONFIG_FILE') else 'skill_store',
        resource_digest=skill.resource_content_digest, integrity=integrity,
        discovered='yes', activated='unknown', executable='yes' if skill.executable else 'no',
        dependency_healthy='unknown', resources=resources,
        metadata={key: metadata[key] for key in ('name', 'description', 'references', 'scripts', 'dependencies')
                  if key in metadata} if isinstance(metadata, dict) else None,
        dependencies=metadata.get('dependencies') if isinstance(metadata, dict) and
            isinstance(metadata.get('dependencies'), list) and
            all(isinstance(item, str) for item in metadata['dependencies']) else None,
        states=States(registered=observed('yes', 'api_skill_store'), loaded=observed('yes', 'api_skill_store')),
    )


def skill_document(name, expected_digest):
    skill = default_store().get(name)
    if not skill:
        raise GateDenied('RESOURCE_NOT_FOUND', 404)
    if skill.resource_content_digest != expected_digest:
        raise GateDenied('RESOURCE_REVISION_CHANGED', 409)
    path = skill.root / 'SKILL.md'
    try:
        if path.is_symlink() or path.resolve().parent != skill.root.resolve():
            raise GateDenied('RESOURCE_NOT_AVAILABLE', 404)
        with path.open('rb') as file:
            body = file.read(65_537)
        if len(body) > 65_536:
            raise GateDenied('RESOURCE_TOO_LARGE', 422)
        if controlled_resource_digest(skill.root) != expected_digest or path.is_symlink():
            raise GateDenied('RESOURCE_REVISION_CHANGED', 409)
        with path.open('rb') as file:
            if file.read(65_537) != body:
                raise GateDenied('RESOURCE_REVISION_CHANGED', 409)
        content = body.decode('utf-8')
    except (OSError, ValueError):
        raise GateDenied('RESOURCE_NOT_AVAILABLE', 404) from None
    # Displayed as literal text by Admin, never interpreted as HTML or links.
    return Document(name=name, resource_digest=expected_digest, render_safe_markdown=content)
