# 东方财富 Push2 API 字段映射参考

> 用于在无财报文件时快速获取 A 股财务数据，填充 `_real_data.json`

## 已验证字段

| 字段 | 含义 | 示例值 | 用途 |
|------|------|--------|------|
| `f41` | 营收同比增速 (%) | 52.72 | `real_signals.revenue_growth` |
| `f57` | 毛利率 (%) | 55.85 | `real_signals.gross_margin` |
| `f9` | PE (TTM) | 85.39 | System B 估值参考 |
| `f45` | 净利润同比 (%) | 注意基期效应可能导致极端值 | 参考，不直接填入 |
| `f40` | 营业收入 (万元) | 季度或 TTM 口径 | 辅助验证 |
| `f20` | 总市值 | — | System B 规模参考 |

## API 调用示例

```python
import urllib.request, json

secids = '0.002428,0.002384,1.688313'  # 深市0. 沪市1.
url = f'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&fields=f41,f57,f9,f40,f20,f45&secids={secids}'

req = urllib.request.Request(url)
req.add_header('User-Agent', 'Mozilla/5.0')
with urllib.request.urlopen(req, timeout=10) as resp:
    data = json.loads(resp.read())
    for item in data['data']['diff']:
        name = item['f14']
        rev_growth = item.get('f41')
        gross_margin = item.get('f57')
        print(f'{name}: 营收同比={rev_growth}%  毛利率={gross_margin}%')
```

## 注意事项

- 深交所代码用 `0.` 前缀，上交所用 `1.`
- `f45` 净利润同比在扭亏场景下会出现极端值（数十万%），建议填入 `system_b_input` 但不要直接用于拐点判定
- 数据实时性为交易日级别，非季报精准数据，但方向可靠
- 所有通过 API 获取的数据应标注来源为 "东方财富行情数据"
