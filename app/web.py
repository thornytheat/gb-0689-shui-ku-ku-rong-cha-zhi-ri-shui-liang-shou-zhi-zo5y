from flask import render_template,request
from app import store
from app.pipeline import run
from app.config import TITLE,MODULES,STAGES,COLUMNS,SAMPLES,DEFAULTS
def view(stage):
    if not 1<=stage<=7: return "页面不存在",404
    run_id=request.args.get("run")
    result=store.fetch(run_id) if run_id else run()
    sample=(SAMPLES/"dirty.csv").read_text(encoding="utf-8-sig")
    data=result["stages"][stage-1]
    curve=result["curve"]
    min_h,max_h=float(curve[0][0]),float(curve[-1][0]);max_v=float(curve[-1][1])
    points=" ".join(f"{45+(float(h)-min_h)/(max_h-min_h)*410:.2f},{210-float(v)/(max_v or 1)*175:.2f}" for h,v in curve)
    measured=" ".join(f"{45+i/(max(len(result['storage'])-1,1))*410:.2f},{210-(float(x['level'])-min_h)/(max_h-min_h)*175:.2f}" for i,x in enumerate(result["storage"]))
    return render_template(f"m{stage}.html",title=TITLE,modules=MODULES,stage=stage,result=result,data=data,
                           sample=sample,defaults=DEFAULTS,columns=COLUMNS,history=store.history(),curve_points=points,level_points=measured)
