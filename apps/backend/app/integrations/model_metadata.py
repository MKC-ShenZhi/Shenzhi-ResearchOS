"""Public supplier catalog adapters used by the Admin display."""
import httpx

from app.core.errors import BusinessError


def autodl_metadata(payload, upstream):
    model = next(row for row in payload['data']['list'] if row['model_name'] == upstream)
    config = model['price_config']
    prices = []

    def append(price, label, schedule=None, lower=0, upper=None):
        for kind, values in (('标准价', price), ('会员价', price.get('member_price'))):
            if values is None:
                continue
            tier = dict(label=label + ' · ' + kind, currency='CNY',
                        input_min_tokens=lower, input_max_tokens=upper, schedule=schedule)
            for key, raw in (('input', 'input_price'), ('output', 'output_price'),
                             ('cache_read', 'input_cached_price')):
                if raw in values:
                    tier[key] = values[raw] / 1000
            prices.append(tier)

    if model['price_type'] == 'json_unit':
        unit = config['json_unit']
        if unit['price_type'] != 'simple_token':
            raise ValueError('Unsupported pricing structure')
        for tier in unit['tiers']:
            append(tier['price'], {'peak': '高峰', 'valley': '空闲'}[tier['tier_name']], unit['description'])
    elif model['price_type'] == 'context_tiered_token':
        for tier in config['context_tiered_token']:
            upper = tier['max_context_length']
            append(tier, '输入长度阶梯', lower=tier['min_context_length'],
                   upper=None if upper == -1 else upper)
    elif model['price_type'] == 'simple_token':
        append(config['simple_token'], '全天')
    else:
        raise ValueError('Unsupported pricing structure')
    if not prices:
        raise ValueError('Empty prices')
    return dict(context_length_display=str(model['context_length']) + 'K',
                documentation_url=model['api_reference_url'],
                source_url='https://www.autodl.art/large-model/market/' + str(model['id']),
                endpoints=model['endpoint_info']['endpoints'], pricing=prices)


def openlux_metadata(payload, upstream):
    if not payload['success']:
        raise ValueError('Supplier catalog unavailable')
    model = next(row for row in payload['data'] if row['model_name'] == upstream)
    if model['quota_type'] != 0 or payload.get('group_model_ratio'):
        raise ValueError('Unsupported pricing overrides')
    prices = []
    for group in model['enable_groups']:
        rate = 2 * model['model_ratio'] * payload['group_ratio'][group]
        tier = dict(label=group, currency='USD', input=round(rate, 8),
                    output=round(rate * model['completion_ratio'], 8))
        if model.get('cache_ratio') is not None:
            tier['cache_read'] = round(rate * model['cache_ratio'], 8)
        if model.get('cache_creation_ratio') is not None:
            tier['cache_write'] = round(rate * model['cache_creation_ratio'], 8)
        prices.append(tier)
    if not prices:
        raise ValueError('Empty prices')
    return dict(pricing=prices, source_url='https://www.openlux.ai/console/models?view=table')


async def fetch_metadata(provider, upstream):
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            if provider == 'autodl':
                response = await client.post('https://www.autodl.art/api/v1/mllm/model/list',
                                             json={'page_index': 1, 'page_size': 100})
                response.raise_for_status()
                payload = response.json()
                if payload['data']['result_total'] > len(payload['data']['list']):
                    raise ValueError('Incomplete supplier catalog')
                return autodl_metadata(payload, upstream)
            response = await client.get('https://www.openlux.ai/api/pricing_new?view=table')
            response.raise_for_status()
            return openlux_metadata(response.json(), upstream)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, StopIteration):
        raise BusinessError(10002, '官网数据读取失败或格式已变化，请稍后重试', 503) from None
