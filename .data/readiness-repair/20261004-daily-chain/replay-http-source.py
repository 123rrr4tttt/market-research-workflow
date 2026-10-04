import json,time,urllib.request,hashlib
from pathlib import Path
E=Path(__file__).resolve().parent
BASE="http://localhost:5173/api/v1"
HEADERS={"X-Project-Key":"readiness_daily_20261004","Content-Type":"application/json"}
def call(path,payload=None):
 r=urllib.request.Request(BASE+path,data=json.dumps(payload).encode() if payload is not None else None,headers=HEADERS)
 with urllib.request.urlopen(r,timeout=45) as response:
  return {"http_status":response.status,"response":json.load(response)}
def save(name,j):
 (E/name).write_text(json.dumps(j,ensure_ascii=False,indent=2))
payload={"source_name":"readiness_daily_public_http","source_kind":"manual","async_mode":True,"enable_extraction":False,"default_doc_type":"raw_note","overwrite_on_uri":True,"fetch_url_when_text_empty":True,"chunk_size":8000,"max_chunks":1,"items":[{"uri":"https://www.rfc-editor.org/rfc/rfc9110.txt","doc_type":"raw_note","title":"RFC 9110 HTTP Semantics"}]}
save("http-source-repair-request.json",payload)
submit=call("/admin/documents/raw-import",payload)
save("http-source-repair-submit.json",submit)
task=submit["response"]["data"]["task_id"]
for _ in range(90):
 status=call("/process/"+task)
 if status["response"]["data"].get("ready"): break
 time.sleep(1)
save("http-source-repair-task.json",status)
data=status["response"]["data"]
assert data["successful"],data
result=data["result"]
assert result["error_count"]==0,result
item=result["items"][0]
assert item["doc_id"]==2,item
readback=call("/admin/documents/2")
d=readback["response"]["data"]
body=d["content"]
meta=d["extracted_data"]["_raw_input"]["material_input"]
profile=d["extracted_data"]["_quality_frontdoor"]["content_extraction"]
summary={"task_id":task,"http_status":readback["http_status"],"doc_id":d["id"],"source_uri":d["uri"],"content_chars":len(body),"content_sha256":hashlib.sha256(body.encode()).hexdigest(),"first_160_chars":body[:160],"last_160_chars":body[-160:],"material_input":meta,"extraction_profile":{k:v for k,v in profile.items() if k not in ("main_content",)},"fetch_status":d["extracted_data"]["_raw_input"].get("fetch_url_status")}
save("http-source-repair-document.json",summary)
assert len(body)>400000,len(body)
assert meta["kind"]=="resource" and meta["mime_type"]=="text/plain",meta
assert profile["main_text_ratio"]==1.0,profile
assert "HTTP Semantics" in body and "http://www.example.com/" in body
print(json.dumps({"task":task,"doc_id":2,"content_chars":len(body),"resource_plaintext_preserved":True}))
