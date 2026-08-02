"""
AST Builder: WorkflowDef IR → complete ast.Module.

The generated module text is fed to ``run_workflow()`` which wraps it in
``async def __workflow__():`` and exec's it in the sandbox.
"""
from __future__ import annotations

import ast
import json as json_module

from .ir import WorkflowDef, PhaseDef, StepDef, VariableDef
from .resolver import ResolveContext, resolve_expr, resolve_prompt
from . import ast_helpers as H


class WorkflowASTBuilder:
    """Build a complete ``ast.Module`` from a :class:`WorkflowDef`."""

    def __init__(self, wf: WorkflowDef):
        self.wf = wf
        self._counter = 0
        # The "previous" var for chaining across serial phases
        self._chain_prev: str | None = None

    # ==================================================================
    # Helpers
    # ==================================================================

    def _next_var(self) -> str:
        self._counter += 1
        return f"_s{self._counter}"

    def _phase_var(self, index: int) -> str:
        return f"_p{index}"

    # ==================================================================
    # Top-level build
    # ==================================================================

    def build(self) -> ast.Module:
        body: list[ast.stmt] = []

        body.append(self._build_meta())
        body.extend(self._build_init())
        body.append(self._build_checkpoint_meta())

        if self.wf.variables:
            body.extend(self._build_variables())

        for i, phase in enumerate(self.wf.phases):
            body.extend(self._build_phase(phase, i))

        body.extend(self._build_cleanup())
        body.append(self._build_return())

        mod = ast.Module(body=body, type_ignores=[])
        ast.fix_missing_locations(mod)
        return mod

    # ==================================================================
    # meta = { ... }
    # ==================================================================

    def _build_meta(self) -> ast.Assign:
        # 生成: meta = {'name': 'sync', 'description': '...', 'phases': [{'title': 'Analyze'}, ...]}
        meta_phases = [H.dict_literal({"title": H.constant(p.title)}) for p in self.wf.phases]
        return H.assign("meta", H.dict_literal({
            "name": H.constant(self.wf.name),
            "description": H.constant(self.wf.description),
            "phases": H.list_literal(meta_phases),
        }))

    # ==================================================================
    # _outputs = {} / _prev = None / checkpoint.save('_meta', ...)
    # ==================================================================

    def _build_init(self) -> list[ast.stmt]:
        return [
            H.assign("_outputs", H.dict_literal()),
            H.assign("_prev", H.none()),
        ]

    def _build_checkpoint_meta(self) -> ast.stmt:
        # 生成: checkpoint.save('_meta', {'workflow': 'sync'})
        # 拆解:
        #   H.name("checkpoint")          → checkpoint
        #   H.method(..., "save", [...])  → checkpoint.save('_meta', {'workflow': 'sync'})
        #   H.expr_stmt(...)              → 将上述表达式包装为独立语句
        return H.expr_stmt(H.method(H.name("checkpoint"), "save", [
            H.constant("_meta"),
            H.dict_literal({"workflow": H.constant(self.wf.name)}),
        ]))

    # ==================================================================
    # Variables: _self_<name> = <prompt>
    # ==================================================================

    def _build_variables(self) -> list[ast.stmt]:
        ctx = ResolveContext()
        stmts: list[ast.stmt] = []
        for v in self.wf.variables:
            stmts.append(H.assign(
                f"_self_{v.name}",
                resolve_prompt(v.prompt, ctx),
            ))
        return stmts

    # ==================================================================
    # Phase dispatcher
    # ==================================================================

    def _build_phase(self, phase: PhaseDef, index: int) -> list[ast.stmt]:
        stmts: list[ast.stmt] = []
        title = phase.title
        pv = self._phase_var(index)
        check_key = title.replace(" ", "_")
        output_name = title.replace(" ", "_")

        stmts.append(H.expr_stmt(H.call_fn("phase", [H.constant(title)])))

        if phase.mode == "serial":
            phase_stmts, result_var = self._build_serial(phase, index, pv, check_key)
        elif phase.mode == "parallel":
            phase_stmts, result_var = self._build_parallel(phase, index, pv)
        elif phase.mode == "dag":
            phase_stmts, result_var = self._build_dag(phase, index, pv, check_key)
        elif phase.mode == "pipeline":
            phase_stmts, result_var = self._build_pipeline(phase, index, pv)
        else:
            raise AssertionError(f"unknown mode: {phase.mode}")

        stmts.extend(phase_stmts)

        # _outputs['Title'] = result
        stmts.append(H.assign(
            H.subscript(H.name("_outputs"), H.constant(output_name)),
            result_var,
        ))

        # Debug log: log('[DEBUG phase=X] result_type=' + str(type(x).__name__) + ' len=' + str(len(str(x))))
        stmts.append(H.expr_stmt(H.call_fn("log", [
            ast.BinOp(
                left=ast.BinOp(
                    left=ast.BinOp(
                        left=H.constant(f"[DEBUG phase={title}] result_type="),
                        op=ast.Add(),
                        right=H.call_fn("str", [
                            H.attribute(H.call_fn("type", [result_var]), "__name__"),
                        ]),
                    ),
                    op=ast.Add(),
                    right=H.constant(" len="),
                ),
                op=ast.Add(),
                right=H.call_fn("str", [
                    H.call_fn("len", [H.call_fn("str", [result_var])]),
                ]),
            ),
        ])))

        # Chain prev for next serial phase (store the variable name string)
        if phase.mode == "serial" and not phase.for_each:
            self._chain_prev = result_var.id if isinstance(result_var, ast.Name) else str(result_var)

        return stmts

    # ==================================================================
    # Serial mode
    # ==================================================================

    def _build_serial(self, phase: PhaseDef, index: int, pv: str, check_key: str) -> tuple[list[ast.stmt], ast.Name]:
        """Build serial phase. Returns (stmts, result_var)."""
        stmts: list[ast.stmt] = []

        prev_var_name = f"{pv}_prev"              # _p1_prev
        results_var = H.name(f"{pv}_results")     # _p1_results

        if phase.for_each:
            # ── serial + for_each ──
            stmts.append(H.assign(
                prev_var_name,
                H.or_expr(
                    H.method(H.name("checkpoint"), "load", [H.constant(check_key)]),
                    H.dict_literal(),
                ),
            ))

            # Checkpoint hit
            hit_body: list[ast.stmt] = [
                H.expr_stmt(H.call_fn("log", [
                    H.constant(f"[checkpoint] Phase {phase.title} CHECKPOINT HIT")
                ])),
                H.assign(results_var, H.subscript(H.name(prev_var_name), H.constant("value"))),
            ]

            # Checkpoint miss — run steps
            items_var = H.name(f"{pv}_items")
            items_expr = resolve_expr(phase.for_each, ResolveContext())
            ctx = ResolveContext(item_var="_item")

            loop_body, last_var = self._build_serial_steps(phase.steps, ctx, indent=False)
            loop_body.append(H.expr_stmt(H.method(results_var, "append", [H.name("_r")])))

            miss_body: list[ast.stmt] = [
                H.assign(items_var, items_expr),
                H.assign(results_var, H.list_literal()),
                H.if_stmt(
                    items_var,
                    [H.for_loop(H.name("_item"), items_var, loop_body)],
                    [H.assign(results_var, H.list_literal())],
                ),
                H.expr_stmt(H.method(H.name("checkpoint"), "save", [
                    H.constant(check_key),
                    H.dict_literal({
                        "value": results_var,
                        "session_path": H.call_fn("agent_session_path", []),
                    }),
                ])),
            ]

            stmts.append(H.if_stmt(
                H.is_not_none(H.get(H.name(prev_var_name), "value")),
                hit_body,
                miss_body,
            ))

            return stmts, results_var

        else:
            # ── serial (no for_each) ──
            stmts.append(H.assign(
                prev_var_name,
                H.or_expr(
                    H.method(H.name("checkpoint"), "load", [H.constant(check_key)]),
                    H.dict_literal(),
                ),
            ))

            # Build step bodies for the else branch
            prev_var = self._chain_prev or "_prev"
            step_stmts, result_var = self._build_serial_steps(
                phase.steps, ResolveContext(prev_var=prev_var),
            )
            step_stmts.append(H.assign("_s_result", result_var))
            step_stmts.append(H.expr_stmt(H.method(H.name("checkpoint"), "save", [
                H.constant(check_key),
                H.dict_literal({
                    "value": H.name("_s_result"),
                    "session_path": H.call_fn("agent_session_path", []),
                }),
            ])))

            result_name = H.name("_s_result")

            # Checkpoint hit
            hit_body: list[ast.stmt] = [
                H.expr_stmt(H.call_fn("log", [
                    H.constant(f"[checkpoint] Phase {phase.title} CHECKPOINT HIT")
                ])),
                H.assign("_s_result", H.subscript(H.name(prev_var_name), H.constant("value"))),
            ]

            stmts.append(H.if_stmt(
                H.is_not_none(H.get(H.name(prev_var_name), "value")),
                hit_body,
                step_stmts,
            ))

            # Stash result for output
            stmts.append(H.assign(results_var, result_name))

            return stmts, results_var

    def _build_serial_steps(self, steps: list[StepDef], ctx: ResolveContext,
                            indent: bool = False) -> tuple[list[ast.stmt], ast.Name]:
        """Compile sequential agent calls with ``${previous}`` chaining.

        Returns (statements, last_result_var).
        """
        stmts: list[ast.stmt] = []
        last_var: ast.Name = H.name(ctx.prev_var)

        for step in steps:
            var_name = self._next_var()
            var = H.name(var_name)

            prompt_expr = resolve_prompt(step.prompt or "", ctx)
            label_expr = resolve_expr(step.label or step.agent, ctx)
            opts = self._build_opts(step, label_expr)
            agent_call = H.call_fn("agent", [prompt_expr, opts])

            stmts.append(H.assign(var_name, H.await_expr(agent_call)))
            stmts.append(H.assign("_r", var))

            ctx.prev_var = var_name
            last_var = var

        return stmts, last_var

    # ==================================================================
    # Parallel mode
    # ==================================================================

    def _build_parallel(self, phase: PhaseDef, index: int, pv: str) -> tuple[list[ast.stmt], ast.Name]:
        stmts: list[ast.stmt] = []
        results_var = H.name(f"{pv}_results")

        if phase.for_each:
            items_var = H.name(f"{pv}_items")
            items_expr = resolve_expr(phase.for_each, ResolveContext())

            # Build lambdas
            ctx = ResolveContext(item_var="it")
            thunks = self._build_parallel_thunks(phase.steps, ctx, capture_item=True)

            # [lambda it=_item: agent(...) for _item in items]
            comp = H.list_comp(
                elt=thunks[0],
                target=H.name("_item"),
                iter=items_var,
            )

            body: list[ast.stmt] = [
                H.assign(items_var, items_expr),
                H.if_stmt(
                    items_var,
                    [H.assign(results_var, H.await_expr(H.call_fn("parallel", [comp])))],
                    [H.assign(results_var, H.list_literal())],
                ),
            ]
            stmts.extend(body)

        else:
            ctx = ResolveContext()
            thunks = self._build_parallel_thunks(phase.steps, ctx, capture_item=False)
            stmts.append(H.assign(
                results_var,
                H.await_expr(H.call_fn("parallel", [H.list_literal(thunks)])),
            ))

        return stmts, results_var

    def _build_parallel_thunks(self, steps: list[StepDef], ctx: ResolveContext,
                               capture_item: bool) -> list[ast.Lambda]:
        """Build lambda thunks for parallel execution."""
        thunks: list[ast.Lambda] = []
        for step in steps:
            prompt_expr = resolve_prompt(step.prompt or "", ctx)
            label_expr = resolve_expr(step.label or step.agent, ctx)
            opts = self._build_opts(step, label_expr)
            agent_call = H.call_fn("agent", [prompt_expr, opts])

            if capture_item:
                # lambda it=_item: agent(...)
                thunk = H.lambda_expr(["it"], agent_call, {"it": H.name("_item")})
            else:
                # lambda: agent(...)
                thunk = H.lambda_expr([], agent_call)

            thunks.append(thunk)
        return thunks

    # ==================================================================
    # DAG mode
    # ==================================================================

    def _build_dag(self, phase: PhaseDef, index: int, pv: str, check_key: str) -> tuple[list[ast.stmt], ast.Name]:
        stmts: list[ast.stmt] = []
        results_var = H.name(f"{pv}_results")

        if phase.for_each:
            prev_tasks_var = H.name(f"{pv}_prev_tasks")
            items_var = H.name(f"{pv}_items")
            dag_tasks_var = H.name(f"{pv}_dag_tasks")
            seed_var = H.name(f"{pv}_seed")
            results_dict_var = H.name(f"{pv}_results_dict")

            # Load previous checkpoint
            stmts.append(H.assign(
                prev_tasks_var,
                H.get(
                    H.or_expr(
                        H.method(H.name("checkpoint"), "load", [H.constant(check_key)]),
                        H.dict_literal(),
                    ),
                    "value",
                    H.dict_literal(),
                ),
            ))

            items_expr = resolve_expr(phase.for_each, ResolveContext())
            stmts.append(H.assign(items_var, items_expr))

            # Build the for-loop body
            loop_body = self._build_dag_for_each_body(phase, pv, prev_tasks_var, dag_tasks_var)

            # Build seed dict comprehension
            # {tid: v['value'] for tid, v in prev_tasks.items() if v.get('value') is not None}
            seed_comp = H.dict_comp(
                key=H.name("tid"),
                value=H.subscript(H.name("v"), H.constant("value")),
                target=ast.Tuple(elts=[H.name("tid"), H.name("v")]),
                iter=H.method(prev_tasks_var, "items"),
                ifs=[H.is_not_none(H.get(H.name("v"), "value"))],
            )

            # Build result list: [_results_dict.get(it.get('id', f'task-{idx}')) for idx, it in enumerate(items)]
            result_list = H.list_comp(
                elt=H.get(
                    results_dict_var,
                    H.method(H.name("it"), "get", [
                        H.constant("id"),
                        ast.JoinedStr(values=[
                            H.constant("task-"),
                            ast.FormattedValue(value=H.name("idx"), conversion=-1),
                        ]),
                    ]),
                ),
                target=ast.Tuple(elts=[H.name("idx"), H.name("it")]),
                iter=H.call_fn("enumerate", [items_var]),
            )

            # _wr save for checkpoint
            wr_var = H.name("_wr")
            save_loop_body = self._build_dag_save_loop(phase, pv, prev_tasks_var, results_dict_var, wr_var)

            # Assemble the if/else
            if_body: list[ast.stmt] = [
                H.assign(dag_tasks_var, H.list_literal()),
                H.for_loop(
                    ast.Tuple(elts=[H.name("idx"), H.name("it")]),
                    H.call_fn("enumerate", [items_var]),
                    loop_body,
                ),
                H.assign(seed_var, seed_comp),
                H.assign(results_dict_var,
                         H.await_expr(H.call_fn("dag", [dag_tasks_var],
                                                [ast.keyword(arg="seed", value=seed_var)]))),
                H.assign(results_var, result_list),
                # Save checkpoint
                H.assign(wr_var, H.dict_literal()),
            ] + save_loop_body + [
                H.expr_stmt(H.method(H.name("checkpoint"), "save", [
                    H.constant(check_key),
                    H.dict_literal({
                        "value": wr_var,
                        "session_path": H.none(),
                    }),
                ])),
            ]

            else_body: list[ast.stmt] = [
                H.assign(results_var, H.list_literal()),
            ]

            stmts.append(H.if_stmt(items_var, if_body, else_body))

        else:
            # dag without for_each — explicit step ids/deps
            task_dicts: list[ast.expr] = []
            for step in phase.steps:
                ctx = ResolveContext()
                prompt_expr = resolve_prompt(step.prompt or "", ctx)
                label_expr = resolve_expr(step.label or step.agent, ctx)
                opts = self._build_opts(step, label_expr)
                agent_call = H.call_fn("agent", [prompt_expr, opts])
                task_fn = H.lambda_expr([], agent_call)

                task_id = resolve_expr(step.id or step.agent, ctx)
                deps = H.list_literal([H.constant(d) for d in (step.depends_on or [])])

                task_dicts.append(H.dict_literal({
                    "id": task_id,
                    "fn": task_fn,
                    "depends_on": deps,
                }))

            dag_tasks_var2 = H.name(f"{pv}_dag_tasks")
            results_dict_var2 = H.name(f"{pv}_results_dict")

            stmts.append(H.assign(dag_tasks_var2, H.list_literal(task_dicts)))
            stmts.append(H.assign(
                results_dict_var2,
                H.await_expr(H.call_fn("dag", [dag_tasks_var2])),
            ))
            stmts.append(H.assign(results_var, results_dict_var2))

        return stmts, results_var

    def _build_dag_for_each_body(self, phase: PhaseDef, pv: str,
                                  prev_tasks_var: ast.Name,
                                  dag_tasks_var: ast.Name) -> list[ast.stmt]:
        """Build the inner for-loop body for DAG + for_each."""
        # tid = it.get('id', f'task-{idx}')
        tid_var = H.name("tid")
        pe_var = H.name("pe")
        it_name = H.name("it")
        idx_name = H.name("idx")

        tid_assign = H.assign(tid_var, H.method(it_name, "get", [
            H.constant("id"),
            ast.JoinedStr(values=[
                H.constant("task-"),
                ast.FormattedValue(value=idx_name, conversion=-1),
            ]),
        ]))

        # pe = prev_tasks.get(tid) or {}
        pe_assign = H.assign(
            pe_var,
            H.or_expr(
                H.get(prev_tasks_var, tid_var),
                H.dict_literal(),
            ),
        )

        # Build the three branches: if / elif / else
        cached_branch = self._build_dag_cached_branch(dag_tasks_var, tid_var, pe_var, it_name)
        resume_branch = self._build_dag_resume_branch(phase, dag_tasks_var, tid_var, pe_var, it_name)
        fresh_branch = self._build_dag_fresh_branch(phase, dag_tasks_var, tid_var, it_name)

        # if pe.get('value') is not None: cached
        # elif pe.get('session_path'): resume
        # else: fresh
        outer_if = H.if_stmt(
            H.is_not_none(H.get(pe_var, "value")),
            cached_branch,
            [H.if_stmt(H.get(pe_var, "session_path"), resume_branch, fresh_branch)],
        )

        return [tid_assign, pe_assign, outer_if]

    def _build_dag_cached_branch(self, dag_tasks_var: ast.Name, tid_var: ast.Name,
                                  pe_var: ast.Name, it_name: ast.Name) -> list[ast.stmt]:
        """Cached value branch: append {'id': tid, 'fn': lambda v=pe['value']: v, ...}."""
        cached_fn = H.lambda_expr(["v"], H.name("v"),
                                  {"v": H.subscript(pe_var, H.constant("value"))})
        task_dict = H.dict_literal({
            "id": tid_var,
            "fn": cached_fn,
            "depends_on": H.get(it_name, "depends_on", H.list_literal()),
        })
        return [H.expr_stmt(H.method(dag_tasks_var, "append", [task_dict]))]

    def _build_dag_resume_branch(self, phase: PhaseDef, dag_tasks_var: ast.Name,
                                  tid_var: ast.Name, pe_var: ast.Name,
                                  it_name: ast.Name) -> list[ast.stmt]:
        """Resume branch: lambda with resume_from session path."""
        stmts: list[ast.stmt] = []
        ctx = ResolveContext(item_var="it2")
        sp_var = H.name("sp")

        for step in phase.steps:
            prompt_expr = resolve_prompt(step.prompt or "", ctx)
            label_expr = resolve_expr(step.label or step.agent, ctx)
            opts = self._build_opts(step, label_expr, {
                "resume_from": sp_var,
            })
            agent_call = H.call_fn("agent", [prompt_expr, opts])
            task_fn = H.lambda_expr(["it2", "sp"], agent_call,
                                    {"it2": it_name,
                                     "sp": H.subscript(pe_var, H.constant("session_path"))})

            task_dict = H.dict_literal({
                "id": tid_var,
                "fn": task_fn,
                "depends_on": H.get(it_name, "depends_on", H.list_literal()),
            })
            stmts.append(H.expr_stmt(H.method(dag_tasks_var, "append", [task_dict])))

        return stmts

    def _build_dag_fresh_branch(self, phase: PhaseDef, dag_tasks_var: ast.Name,
                                 tid_var: ast.Name, it_name: ast.Name) -> list[ast.stmt]:
        """Fresh branch: lambda with clean agent call."""
        stmts: list[ast.stmt] = []
        ctx = ResolveContext(item_var="it2")

        for step in phase.steps:
            prompt_expr = resolve_prompt(step.prompt or "", ctx)
            label_expr = resolve_expr(step.label or step.agent, ctx)
            opts = self._build_opts(step, label_expr)
            agent_call = H.call_fn("agent", [prompt_expr, opts])
            task_fn = H.lambda_expr(["it2"], agent_call, {"it2": it_name})

            task_dict = H.dict_literal({
                "id": tid_var,
                "fn": task_fn,
                "depends_on": H.get(it_name, "depends_on", H.list_literal()),
            })
            stmts.append(H.expr_stmt(H.method(dag_tasks_var, "append", [task_dict])))

        return stmts

    def _build_dag_save_loop(self, phase: PhaseDef, pv: str,
                              prev_tasks_var: ast.Name,
                              results_dict_var: ast.Name,
                              wr_var: ast.Name) -> list[ast.stmt]:
        """Build the save loop for DAG results::

            for idx, it in enumerate(items):
                tid = it.get('id', f'task-{idx}')
                r = results_dict.get(tid)
                cs = agent_session_path()
                old_s = prev_tasks.get(tid, {}).get('session_path')
                _wr[tid] = {'value': r, 'session_path': cs if r is not None else old_s}
        """
        items_var = H.name(f"{pv}_items")
        tid_var2 = H.name("tid")
        r_var = H.name("r")
        cs_var = H.name("cs")
        old_s_var = H.name("old_s")

        tid_assign = H.assign(tid_var2, H.method(H.name("it"), "get", [
            H.constant("id"),
            ast.JoinedStr(values=[
                H.constant("task-"),
                ast.FormattedValue(value=H.name("idx"), conversion=-1),
            ]),
        ]))

        return [
            H.for_loop(
                ast.Tuple(elts=[H.name("idx"), H.name("it")]),
                H.call_fn("enumerate", [items_var]),
                [
                    tid_assign,
                    H.assign(r_var, H.get(results_dict_var, tid_var2)),
                    H.assign(cs_var, H.call_fn("agent_session_path", [])),
                    H.assign(old_s_var, H.get(
                        H.get(prev_tasks_var, tid_var2, H.dict_literal()),
                        "session_path",
                    )),
                    H.assign(
                        H.subscript(wr_var, tid_var2),
                        H.dict_literal({
                            "value": r_var,
                            "session_path": H.ternary(
                                H.is_not_none(r_var), cs_var, old_s_var,
                            ),
                        }),
                    ),
                ],
            ),
        ]

    # ==================================================================
    # Pipeline mode
    # ==================================================================

    def _build_pipeline(self, phase: PhaseDef, index: int, pv: str) -> tuple[list[ast.stmt], ast.Name]:
        stmts: list[ast.stmt] = []
        results_var = H.name(f"{pv}_results")

        items_var = H.name(f"{pv}_items")
        items_expr = resolve_expr(phase.for_each, ResolveContext()) if phase.for_each else H.list_literal()

        # Build stage lambdas: lambda _prev, _orig, _idx: agent(...)
        stages: list[ast.Lambda] = []
        for step in phase.steps:
            ctx = ResolveContext(prev_var="_prev", item_var="_orig")
            prompt_expr = resolve_prompt(step.prompt or "", ctx)
            label_expr = resolve_expr(step.label or step.agent, ctx)

            # Build opts dict manually to include label + agent
            opts_pairs: dict[str, ast.expr] = {
                "label": label_expr,
                "agent": H.constant(step.agent),
            }
            if step.output_schema:
                opts_pairs["schema"] = H.constant(json_module.dumps(step.output_schema))

            agent_call = H.call_fn("agent", [prompt_expr, H.dict_literal(opts_pairs)])
            stage = H.lambda_expr(["_prev", "_orig", "_idx"], agent_call)
            stages.append(stage)

        # await pipeline(items, stage1, stage2, ...)
        pipeline_call = H.await_expr(H.call_fn("pipeline", [items_var] + stages))

        if phase.for_each:
            stmts.append(H.assign(items_var, items_expr))
            stmts.append(H.if_stmt(
                items_var,
                [H.assign(results_var, pipeline_call)],
                [H.assign(results_var, H.list_literal())],
            ))
        else:
            stmts.append(H.assign(results_var, pipeline_call))

        return stmts, results_var

    # ==================================================================
    # Cleanup + Return
    # ==================================================================

    def _build_cleanup(self) -> list[ast.stmt]:
        return [
            H.if_stmt(
                ast.UnaryOp(op=ast.Not(), operand=H.get(H.name("args"), "keep_checkpoint")),
                [H.expr_stmt(H.method(H.name("checkpoint"), "clear"))],
            ),
        ]

    def _build_return(self) -> ast.Return:
        return H.return_stmt(H.call_fn("dict", [H.name("_outputs")]))

    # ==================================================================
    # Agent call helpers
    # ==================================================================

    def _build_opts(self, step: StepDef, label_expr: ast.expr,
                    extra: dict[str, ast.expr] | None = None) -> ast.expr:
        """Build the opts dict for an ``agent()`` call."""
        pairs: dict[str, ast.expr] = {
            "label": label_expr,
            "agent": H.constant(step.agent),
        }
        if step.output_schema:
            pairs["schema"] = H.constant(json_module.dumps(step.output_schema))
        if extra:
            pairs.update(extra)
        return H.dict_literal(pairs)
