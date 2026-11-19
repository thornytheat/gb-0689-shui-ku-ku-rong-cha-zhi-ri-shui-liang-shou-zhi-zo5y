from pathlib import Path
TITLE = '水库库容插值与日水量收支'
SHORT = 'reservoir-ledger'
STAGES = ['receive', 'curve', 'integrate', 'storage', 'budget', 'review', 'trace']
MODULES = ['测站采信', '曲线校核', '流量积分', '库容换算', '日收支', '异常复核', '重算留痕']
COLUMNS = {'id': '测次号', 'station': '测站', 'time': '观测 UTC', 'level': '水位 m', 'inflow': '入流 m³/s', 'outflow': '出流 m³/s', 'volume': '库容 m³', 'start': '开始 UTC', 'end': '结束 UTC', 'in_m3': '入库 m³', 'out_m3': '出库 m³', 'storage_change': '库容变化 m³', 'residual': '收支差 m³', 'date': '日期 +08', 'coverage_hours': '覆盖 h', 'state': '状态', 'code': '原因码', 'reason': '原因', 'line': '行号', 'count': '数量'}
DEFAULTS = {'max_gap_hours': '2', 'tolerance_m3': '500', 'curve': [['100', '0'], ['102', '30000'], ['105', '100000'], ['108', '220000']]}
RULE_VERSION = "2026.11.18-v1"
SAMPLES = Path(__file__).resolve().parent.parent / "sample_data"
MAX_BYTES = 4 * 1024 * 1024

COLUMNS.update({'key':'业务键','detail':'依据','hours':'缺口 h','flow_unit':'流量单位','version':'版本'})

COLUMNS['arrival']='到达顺序'
