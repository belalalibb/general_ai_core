"""R197 live DOM probe: real server (python -m apps.main, demo principal), real Chromium.
Records: picker options after session, the execute request body with a chosen template,
and the served /v1/templates rows. Evidence only; no secrets."""
import json, os, socket, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright
ROOT="/home/user/webapp"
s=socket.socket(); s.bind(("127.0.0.1",0)); port=s.getsockname()[1]; s.close()
env={k:v for k,v in os.environ.items() if not k.startswith(("GROQ_API_KEY","GSK_API_KEY","GW_GROQ","OPENAI_API_KEY","ANTHROPIC_API_KEY")) and k not in ("DATABASE_URL","REDIS_URL")}
env.update({"HOST":"127.0.0.1","PORT":str(port),"DEV_DEMO_PRINCIPAL":"1","LOG_LEVEL":"warning","PYTHONUNBUFFERED":"1","PLAYWRIGHT_BROWSERS_PATH":"/home/user/.cache/ms-playwright"})
proc=subprocess.Popen([sys.executable,"-m","apps.main"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
base=f"http://127.0.0.1:{port}"
out={"base":"http://127.0.0.1:<ephemeral>","head":subprocess.check_output(["git","rev-parse","--short=8","HEAD"],cwd=ROOT,text=True).strip()}
try:
    deadline=time.time()+40
    while time.time()<deadline:
        try: urllib.request.urlopen(base+"/healthz",timeout=1); break
        except Exception: time.sleep(0.5)
    out["served_templates"]=json.loads(urllib.request.urlopen(base+"/v1/templates").read())
    with sync_playwright() as p:
        b=p.chromium.launch(); page=b.new_page()
        captured=[]
        trace=[]
        def on_req(r):
            if "/v1/" in r.url:
                row={"method":r.method,"url":r.url.replace(base,""),"post":r.post_data}
                trace.append(row)
                if "/v1/execute" in r.url or "/v1/templates" in r.url: captured.append(row)
        def on_resp(r):
            if "/v1/execute" in r.url or "/v1/templates" in r.url:
                try: body=r.json()
                except Exception: body=None
                for row in captured:
                    if row["url"]==r.url.replace(base,"") and "status" not in row:
                        row["status"]=r.status; row["response_status"]=(body or {}).get("status") if isinstance(body,dict) else None
                        row["response_execution_id"]=(body or {}).get("execution_id") if isinstance(body,dict) else None; break
        page.on("request", on_req); page.on("response", on_resp)
        out["request_trace_in_order"]=trace
        page.goto(base+"/app/"); page.wait_for_selector("#main-view:not([hidden])",timeout=15000)
        page.wait_for_function("document.querySelectorAll('#ask-template option').length > 1",timeout=10000)
        out["picker_options"]=page.eval_on_selector_all("#ask-template option","els=>els.map(e=>({value:e.value,text:e.textContent}))")
        out["ask_error_hidden"]=page.eval_on_selector("#ask-error","e=>e.hidden")
        # choose the template, submit an ask, capture the request body
        page.fill("#ask-input","probe: template mode")
        page.select_option("#ask-template", out["picker_options"][1]["value"])
        out["select_value_before_submit"]=page.eval_on_selector("#ask-template","e=>e.value")
        page.click("#ask-submit"); page.wait_for_timeout(2500)
        out["requests_with_template"]=[r for r in trace if "/v1/execute" in r["url"]]
        out["result_visible"]=page.eval_on_selector("#ask-result","e=>!e.hidden")
        out["result_text_head"]=(page.eval_on_selector("#ask-result","e=>e.textContent")or"")[:400]
        # no template chosen => no execution_strategy
        n_before=len(trace)
        page.select_option("#ask-template","")
        page.click("#ask-submit"); page.wait_for_timeout(1500)
        out["requests_without_template"]=[r for r in trace[n_before:] if "/v1/execute" in r["url"]]
        b.close()
finally:
    proc.terminate()
print(json.dumps(out,indent=1,ensure_ascii=False))
