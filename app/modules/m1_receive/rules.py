from app.normalize import rows_from
from app.reasons import rejected
def receive(raw):
    result=rows_from(raw,['id','station','time','level','inflow','outflow','flow_unit','version']);good=[]
    for row in result['raw']:
        if not row['id'] or not row['station']:result['quarantine'].append(rejected(row,'MISSING','测次或测站缺失'))
        else:good.append(row)
    result['records']=good;return result
