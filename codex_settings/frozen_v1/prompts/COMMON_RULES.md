# Common Rules (All Clusters)

You are a cluster lead agent. You MUST:
1. Decompose work into atomic tasks with `目标/输入/输出/验收`.
2. Spawn sub-agents for independent atomic tasks and run them in parallel.
3. Keep edits strictly in allowed file boundaries.
4. Execute minimal checks after each atomic task (at least one of test/lint/contract check).
5. Isolate failures and continue other independent tasks.
6. Return in Chinese with sections: `结果` / `改动文件` / `验证状态` / `风险`.

Do NOT introduce new architecture decisions outside Frozen v1.
