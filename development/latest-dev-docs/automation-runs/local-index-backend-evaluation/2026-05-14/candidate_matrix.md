# Local Index Backend Candidate Matrix

| candidate | local client installed | entered benchmark | full text | vector | hybrid | metadata filter | note |
|---|---:|---:|---:|---:|---:|---|---|
| LanceDB | True | True | True | True | True | True | local lightweight table/vector/full-text candidate |
| Qdrant | False | False | False | True | True | True | AI-native dense/sparse/hybrid retrieval candidate |
| Meilisearch | False | False | True | True | True | True | full-text plus AI/hybrid search candidate |
| Typesense | False | False | True | True | True | True | fast document search with vector/hybrid candidate |
| Weaviate | False | False | True | True | True | True | full vector database with BM25F hybrid candidate |
| SQLite FTS5 baseline | True | True | True | False | False | True | built-in local full-text baseline |
| YaCy local | None | False | True | False | False | limited | baseline only; previous smoke proved push -> resource=local hit |
