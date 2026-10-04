import json, time, urllib.request, hashlib, uuid
from pathlib import Path
E=Path(__file__).resolve().parent
BASE="http://localhost:5173/api/v1"
PROJECT="readiness_daily_20261004"
def call(path,payload=None,headers=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,headers={"X-Project-Key":PROJECT,"Content-Type":"application/json",**(headers or {})})
    with urllib.request.urlopen(request,timeout=30) as r:
        return {"http_status":r.status,"response":json.load(r)}
def save(name,data):
    (E/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")
health=call("/health/deep")
save("live-health-after-reload.json",health)
assert health["response"]["status"]=="ok",health
marker="MRW structure user-chain "+str(uuid.uuid4())
body=marker+"\nLocal material verifies API dispatch, independent worker and persistent readback."
uri="urn:mrw:structure-check:"+str(uuid.uuid4())
payload={"source_name":"structure_user_chain","source_kind":"manual","async_mode":True,"enable_extraction":False,"default_doc_type":"raw_note","fetch_url_when_text_empty":False,"items":[{"uri":uri,"title":marker,"text":body,"doc_type":"raw_note"}]}
submit=call("/admin/documents/raw-import",payload)
save("live-material-submit.json",submit)
task_id=submit["response"]["data"]["task_id"]
for _ in range(60):
    observed=call("/process/"+task_id)
    if observed["response"]["data"].get("ready"):break
    time.sleep(1)
save("live-material-task.json",observed)
data=observed["response"]["data"]
assert data["successful"],data
result=data["result"]
assert result["error_count"]==0,result
doc_id=result["items"][0]["doc_id"]
readback=call("/admin/documents/"+str(doc_id))
save("live-material-readback.json",readback)
doc=readback["response"]["data"]
assert doc["content"]==body and doc["uri"]==uri,doc
fresh=call("/admin/documents/"+str(doc_id))
assert fresh["response"]["data"]["content"]==body
old=call("/admin/documents/1")
assert "MRW daily full-chain policy" in old["response"]["data"]["content"]
summary={"status":"passed","scope":"local single-user","project":PROJECT,"task_id":task_id,"document_id":doc_id,"content_sha256":hashlib.sha256(body.encode()).hexdigest(),"fresh_readback_matches":True,"original_policy_preserved":True,"provider_calls_requested":0}
save("live-user-chain-result.json",summary)
print(json.dumps(summary,ensure_ascii=False))
