const API = 'http://127.0.0.1:8899/api'

const { createApp } = Vue

createApp({
  data() {
    return {
      apiOnline: false,
      projects: [],
      selectedProject: '',
      commits: [],
      selectedCommit: '',
      commitDetail: null,
      loading: false,
      syncing: false,
      syncResult: null,
      streamText: '',
      streamTools: [],
      syncMode: 'chain',  // 'single' | 'chain' | 'workflow'
      chainSteps: [],
      wfAgents: [],     // workflow agent status list
      wfPhase: '',      // current workflow phase
      failures: [],     // [{ revision, commit_message, phases, updated_at }]
      keepCheckpoint: false,  // debug: skip checkpoint cleanup
      showAddProject: false,
      newProject: { name: '', path: '', start_revision: '' },
      addError: '',
      models: [],
      selectedModel: '',
      newModel: { name: '', provider: '', model_id: '', base_url: '', api_key: '' },
      modelError: '',
      currentView: 'commits',
      settingsTab: 'models',
      filters: [],
      filterEnabled: true,
      newFilter: { type: 'path', pattern: '', description: '' },
      filterError: '',
      checking: false,
      qualityReport: null,
      fixing: false,
      cronJobs: [],
      newCronJob: { task: 'quality_check', job_id: '', name: '', project_path: '', minute: '0', hour: '2', day: '*', month: '*', day_of_week: '*' },
      generating: false,
      genProgress: [],
      selectedProjectObj: null,
    }
  },

  async mounted() {
    await this.checkHealth()
    await Promise.all([this.loadProjects(), this.loadModels()])
    document.addEventListener('keydown', this._onKeydown)
  },

  beforeUnmount() {
    document.removeEventListener('keydown', this._onKeydown)
  },

  watch: {
    showAddProject(val) {
      if (val) {
        this.$nextTick(() => {
          const input = this.$el.querySelector('.modal-overlay input')
          if (input) input.focus()
        })
      }
    },
  },

  methods: {
    _onKeydown(e) {
      if (e.key === 'Escape' && this.showAddProject) {
        this.closeAddProject()
      }
    },

    async checkHealth() {
      try { const r = await fetch(`${API}/health`); this.apiOnline = r.ok } catch { this.apiOnline = false }
    },

    // ── Projects ────────────────────────────────────────────────────
    async loadProjects() {
      try { const r = await fetch(`${API}/projects`); this.projects = await r.json() } catch (e) { console.error(e) }
    },

    openSettings() { this.currentView = 'settings'; this.settingsTab = 'models' },

    async selectProject(name) {
      this.selectedProject = name; this.selectedCommit = ''; this.commitDetail = null; this.syncResult = null
      this.qualityReport = null; this.genProgress = []
      this.selectedProjectObj = this.projects.find(p => p.name === name) || null
      this.currentView = 'commits'
      await Promise.all([this.refreshCommits(), this.loadFilters(), this.refreshFailures()])
    },

    async refreshCommits() {
      if (!this.selectedProject) return
      this.loading = true
      try { const r = await fetch(`${API}/projects/${this.selectedProject}/commits`); this.commits = await r.json() } catch (e) { console.error(e) }
      this.loading = false
    },

    async refreshFailures() {
      if (!this.selectedProject) return
      try {
        const r = await fetch(`${API}/projects/${this.selectedProject}/workflow-failures`)
        this.failures = (await r.json()).failures || []
      } catch (e) { console.error(e) }
    },

    getFailure(rev) {
      return this.failures.find(f => f.revision === rev) || null
    },

    async startFresh(rev) {
      const f = this.getFailure(rev)
      await fetch(`${API}/projects/${this.selectedProject}/workflow-sync/${rev}/checkpoint`, { method: 'DELETE' })
      this.failures = this.failures.filter(f => f.revision !== rev)
      this.keepCheckpoint = false
      if (f?.workflow === 'fix_quality') {
        this.runQualityFix()
      } else {
        this.syncCommit(rev)
      }
    },

    async previewCommit(rev) {
      this.selectedCommit = rev; this.syncResult = null
      try { const r = await fetch(`${API}/projects/${this.selectedProject}/commits/${rev}`); this.commitDetail = await r.json() } catch (e) { console.error(e) }
    },

    async syncCommit(rev) {
      this.syncing = true; this.syncResult = null; this.streamText = ''; this.streamTools = []; this.chainSteps = []; this.wfAgents = []; this.wfPhase = ''
      this.streamText = '正在启动同步...\n'
      console.log('[syncCommit] syncMode:', this.syncMode, 'rev:', rev)
      if (this.syncMode === 'workflow') {
        const f = this.getFailure(rev)
        await this._workflowSyncStream(rev, f?.workflow)
      } else if (this.syncMode === 'chain') {
        console.log('[syncCommit] → CHAIN 链式模式')
        await this._chainSyncStream(rev)
      } else {
        console.log('[syncCommit] → 单 Agent 模式')
        await this._syncStream(rev)
      }
    },

    async syncAll() {
      this.syncing = true; this.syncResult = null; this.streamText = ''; this.streamTools = []
      const body = this.selectedModel ? JSON.stringify({ model: this.selectedModel }) : undefined
      try {
        const r = await fetch(`${API}/projects/${this.selectedProject}/sync-all`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        })
        const result = await r.json()
        this.syncResult = { success: true, wiki_pages_modified: result.results.flatMap(r => r.wiki_pages_modified) }
        this.selectedCommit = ''
        this.commitDetail = null
      } catch (e) { this.syncResult = { success: false, error: e.message } }
      this.syncing = false
      await this.loadProjects(); await this.refreshCommits()
    },

    async _chainSyncStream(rev) {
      this.streamText = '[CHAIN] 正在启动 diff-analyzer → wiki-planner → wiki-writer 链式同步...\n'
      const body = this.selectedModel ? JSON.stringify({ model: this.selectedModel }) : undefined
      const url = `${API}/projects/${this.selectedProject}/chain-sync/${rev}/stream`
      console.log('[chain] 请求:', url)
      try {
        const r = await fetch(url, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        })
        const reader = r.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n'); buf = lines.pop()
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6))
                // ── Agent events (same format as single-agent stream) ──
                if (evt.type === 'message_update' && evt.text) {
                  this.streamText += evt.text
                } else if (evt.type === 'tool_execution_start') {
                  this.streamTools.push({ name: evt.tool, status: 'running', args: evt.args })
                } else if (evt.type === 'tool_execution_end') {
                  const t = this.streamTools.findLast(x => x.name === evt.tool && x.status === 'running')
                  if (t) t.status = evt.is_error ? 'error' : 'done'
                // ── Chain step events ──
                } else if (evt.type === 'chain_step_start') {
                  console.log('[chain] step_start:', evt.agent, evt.step_index + 1, '/', evt.data?.total)
                  this.streamText = ''; this.streamTools = []  // Clear for new step
                  this.chainSteps.push({ agent: evt.agent, status: 'running', step: evt.step_index + 1, total: evt.data?.total })
                } else if (evt.type === 'chain_step_end') {
                  console.log('[chain] step_end:', evt.agent, 'output preview:', evt.data?.output?.slice(0, 80))
                  const s = this.chainSteps.findLast(x => x.agent === evt.agent && x.status === 'running')
                  if (s) { s.status = 'done'; s.output = evt.data?.output }
                } else if (evt.type === 'chain_step_error') {
                  console.error('[chain] step_error:', evt.agent, evt.data?.error)
                  const s = this.chainSteps.findLast(x => x.agent === evt.agent && x.status === 'running')
                  if (s) { s.status = 'error'; s.error = evt.data?.error }
                } else if (evt.type === 'chain_done') {
                  console.log('[chain] done:', evt.success, 'error:', evt.error)
                  this.syncResult = evt
                  this.syncing = false
                  if (evt.success) {
                    this.selectedCommit = ''
                    this.commitDetail = null
                    await this.loadProjects()
                    await this.refreshCommits()
                  }
                  return
                }
              } catch(_) {}
            }
          }
        }
      } catch (e) {
        this.syncResult = { success: false, error: e.message }
        this.syncing = false
      }
    },

    async _workflowSyncStream(rev, workflowName) {
      this.streamText = ''
      const bodyObj = {}
      if (this.selectedModel) bodyObj.model = this.selectedModel
      if (this.keepCheckpoint) bodyObj.keep_checkpoint = true
      if (workflowName) bodyObj.workflow = workflowName
      const body = Object.keys(bodyObj).length > 0 ? JSON.stringify(bodyObj) : undefined
      const url = `${API}/projects/${this.selectedProject}/workflow-sync/${rev}/stream`
      console.log('[workflow] 请求:', url)
      try {
        const r = await fetch(url, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        })
        const reader = r.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n'); buf = lines.pop()
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6))
                // Route events to the matching agent
                const sub = evt._subagent
                let agent = sub ? this.wfAgents.findLast(x => x.label === sub) : null

                if (evt.type === 'workflow_phase') {
                  this.wfPhase = evt.phase
                } else if (evt.type === 'workflow_agent_start') {
                  agent = { label: evt.label, phase: evt.phase, status: 'running', log: '', tools: [] }
                  this.wfAgents.push(agent)
                } else if (evt.type === 'workflow_agent_end') {
                  if (!agent) agent = this.wfAgents.findLast(x => x.label === evt.label && x.status === 'running')
                  if (agent) { agent.status = evt.error ? 'error' : 'done'; agent.error = evt.error }
                } else if (evt.type === 'message_update' && evt.text) {
                  if (agent) { agent.log += evt.text }
                } else if (evt.type === 'tool_execution_start') {
                  if (agent) { agent.tools.push({ name: evt.tool, status: 'running', args: evt.args }) }
                } else if (evt.type === 'tool_execution_end') {
                  if (agent) {
                    const t = agent.tools.findLast(x => x.name === evt.tool && x.status === 'running')
                    if (t) t.status = evt.is_error ? 'error' : 'done'
                  }
                } else if (evt.type === 'workflow_done') {
                  console.log('[workflow] done:', evt.success, 'agents:', evt.agent_count, 'duration:', evt.duration_ms, 'ms')
                  this.syncResult = { success: evt.success, error: evt.error, pages: evt.result?.phase3_write?.results || [] }
                  this.syncing = false
                  await this.refreshFailures()
                  if (evt.success) {
                    this.selectedCommit = ''
                    this.commitDetail = null
                    await this.loadProjects()
                    await this.refreshCommits()
                  }
                  return
                }
              } catch(_) {}
            }
          }
        }
      } catch (e) {
        this.syncResult = { success: false, error: e.message }
        this.syncing = false
      }
    },

    async _syncStream(rev) {
      this.streamText = '[单Agent] 正在同步...\n'
      const body = this.selectedModel ? JSON.stringify({ model: this.selectedModel }) : undefined
      const url = `${API}/projects/${this.selectedProject}/sync/${rev}/stream`
      console.log('[single] 请求:', url)
      try {
        const r = await fetch(url, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        })
        const reader = r.body.getReader()
        const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n'); buf = lines.pop()
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6))
                if (evt.type !== 'chain_step_end' && evt.type !== 'chain_done') {
                  console.log('[chain] SSE event:', evt.type, evt.type === 'agent_event' ? '' : JSON.stringify(evt).slice(0, 120))
                }
                if (evt.type === 'message_update' && evt.text) {
                  this.streamText += evt.text
                } else if (evt.type === 'tool_execution_start') {
                  this.streamTools.push({ name: evt.tool, status: 'running', args: evt.args })
                } else if (evt.type === 'tool_execution_end') {
                  const t = this.streamTools.findLast(x => x.name === evt.tool && x.status === 'running')
                  if (t) t.status = evt.is_error ? 'error' : 'done'
                } else if (evt.type === 'sync_done') {
                  this.syncResult = evt
                  this.syncing = false
                  if (evt.success) {
                    this.selectedCommit = ''
                    this.commitDetail = null
                    await this.loadProjects()
                    await this.refreshCommits()
                  }
                  return
                }
              } catch(_) {}
            }
          }
        }
      } catch (e) {
        this.syncResult = { success: false, error: e.message }
        this.syncing = false
      }
    },

    closeAddProject() {
      this.showAddProject = false
      this.addError = ''
    },

    async addProject() {
      this.addError = ''
      try {
        const r = await fetch(`${API}/projects`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newProject),
        })
        if (r.ok) { this.showAddProject = false; this.newProject = { name: '', path: '', start_revision: '' }; await this.loadProjects() }
        else { const err = await r.json(); this.addError = err.detail || '添加失败' }
      } catch (e) { this.addError = e.message }
    },
    async deleteProject(name) {
      if (!confirm(`确定要删除项目 "${name}" 吗？`)) return
      try {
        await fetch(`${API}/projects/${encodeURIComponent(name)}`, { method: 'DELETE' })
        if (this.selectedProject === name) {
          this.selectedProject = ''; this.commits = []; this.commitDetail = null
        }
        await this.loadProjects()
      } catch (e) { console.error(e) }
    },

    // ── Models ───────────────────────────────────────────────────────
    async loadModels() {
      try {
        const r = await fetch(`${API}/models`); this.models = await r.json()
        if (!this.selectedModel && this.models.length > 0) {
          // Auto-select first available model
          this.selectedModel = `${this.models[0].provider}:${this.models[0].model_id}`
        }
      } catch (e) { console.error(e) }
    },



    async addModel() {
      this.modelError = ''
      try {
        const r = await fetch(`${API}/models`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newModel),
        })
        if (r.ok) {
          await this.loadModels()
          this.newModel = { name: '', provider: '', model_id: '', base_url: '', api_key: '' }
        } else {
          const err = await r.json(); this.modelError = err.detail || '添加失败'
        }
      } catch (e) { this.modelError = e.message }
    },

    async deleteModel(m) {
      if (!confirm(`确定删除模型 "${m.name}"?`)) return
      try {
        await fetch(`${API}/models/${encodeURIComponent(m.provider)}/${encodeURIComponent(m.model_id)}`, { method: 'DELETE' })
        await this.loadModels()
      } catch (e) { console.error(e) }
    },

    // ── Filters ─────────────────────────────────────────────────────
    async loadFilters() {
      if (!this.selectedProject) return
      try {
        const r = await fetch(`${API}/projects/${this.selectedProject}/filters`)
        this.filters = await r.json()
      } catch (e) { console.error(e) }
    },

    async addFilter() {
      this.filterError = ''
      try {
        const r = await fetch(`${API}/projects/${this.selectedProject}/filters`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newFilter),
        })
        if (r.ok) { this.newFilter = { type: 'path', pattern: '', description: '' }; await this.loadFilters() }
        else { const err = await r.json(); this.filterError = err.detail || '添加失败' }
      } catch (e) { this.filterError = e.message }
    },

    async deleteFilter(index) {
      try {
        await fetch(`${API}/projects/${this.selectedProject}/filters/${index}`, { method: 'DELETE' })
        await this.loadFilters()
      } catch (e) { console.error(e) }
    },

    async toggleFilter() {
      try {
        await fetch(`${API}/projects/${this.selectedProject}/filters/toggle`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: this.filterEnabled }),
        })
      } catch (e) { console.error(e) }
    },

    // ── Full Generation ───────────────────────────────────────────────
    async generateWiki() {
      this.generating = true; this.genProgress = []
      const url = `${API}/projects/${this.selectedProject}/generate/stream`
      const body = this.selectedModel ? JSON.stringify({ model: this.selectedModel }) : undefined
      console.log('[gen] 请求:', url)
      try {
        const r = await fetch(url, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
        })
        const reader = r.body.getReader(); const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n'); buf = lines.pop()
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6))
                if (evt.type === 'gen_page_start') {
                  this.genProgress.push({ path: evt.page_path, status: 'running', index: evt.page_index + 1, total: evt.data?.total })
                } else if (evt.type === 'gen_page_done') {
                  const g = this.genProgress.findLast(x => x.path === evt.page_path && x.status === 'running')
                  if (g) g.status = 'done'
                } else if (evt.type === 'gen_page_error') {
                  const g = this.genProgress.findLast(x => x.path === evt.page_path && x.status === 'running')
                  if (g) { g.status = 'error'; g.error = evt.data?.error }
                } else if (evt.type === 'gen_done') {
                  console.log('[gen] done:', evt.pages_created?.length, 'pages')
                  this.generating = false
                  if (evt.success) {
                    this.selectedProjectObj.has_wiki = true
                    await this.loadProjects(); await this.refreshCommits()
                  }
                  return
                }
              } catch(_) {}
            }
          }
        }
      } catch (e) {
        this.generating = false
        console.error('[gen] failed:', e)
      }
    },

    // ── Quality Check ──────────────────────────────────────────────────
    async checkQuality() {
      this.checking = true; this.qualityReport = null
      try {
        const r = await fetch(`${API}/projects/${this.selectedProject}/quality-check`, {
          method: 'POST',
        })
        this.qualityReport = await r.json()
      } catch (e) {
        this.qualityReport = { total_issues: -1, issues: [], error: e.message }
      }
      this.checking = false
    },

    // ── Cron ──────────────────────────────────────────────────────────
    async loadCronJobs() {
      try { const r = await fetch(`${API}/cron/jobs`); this.cronJobs = (await r.json()).jobs || [] } catch (e) { console.error(e) }
    },
    async addCronJob() {
      try {
        await fetch(`${API}/cron/jobs`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newCronJob),
        })
        this.newCronJob = { task: 'quality_check', job_id: '', name: '', project_path: '', minute: '0', hour: '2', day: '*', month: '*', day_of_week: '*' }
        await this.loadCronJobs()
      } catch (e) { console.error(e) }
    },
    async removeCronJob(jobId) {
      try {
        await fetch(`${API}/cron/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' })
        await this.loadCronJobs()
      } catch (e) { console.error(e) }
    },

    async runQualityFix() {
      this.fixing = true; this.wfAgents = []; this.wfPhase = ''; this.syncResult = null
      const bodyObj = {}
      if (this.selectedModel) bodyObj.model = this.selectedModel
      if (this.keepCheckpoint) bodyObj.keep_checkpoint = true
      const body = Object.keys(bodyObj).length > 0 ? JSON.stringify(bodyObj) : undefined
      const url = `${API}/projects/${this.selectedProject}/quality-fix/stream`
      try {
        const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body })
        const reader = r.body.getReader(); const decoder = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += decoder.decode(value, { stream: true })
          const lines = buf.split('\n'); buf = lines.pop()
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6))
                const sub = evt._subagent
                let agent = sub ? this.wfAgents.findLast(x => x.label === sub) : null
                if (evt.type === 'workflow_phase') {
                  this.wfPhase = evt.phase
                } else if (evt.type === 'workflow_agent_start') {
                  this.wfAgents.push({ label: evt.label, phase: evt.phase, status: 'running', log: '', tools: [] })
                } else if (evt.type === 'workflow_agent_end') {
                  if (!agent) agent = this.wfAgents.findLast(x => x.label === evt.label && x.status === 'running')
                  if (agent) { agent.status = evt.error ? 'error' : 'done'; agent.error = evt.error }
                } else if (evt.type === 'message_update' && evt.text) {
                  if (agent) { agent.log += evt.text }
                } else if (evt.type === 'tool_execution_start') {
                  if (agent) { agent.tools.push({ name: evt.tool, status: 'running', args: evt.args }) }
                } else if (evt.type === 'tool_execution_end') {
                  if (agent) { const t = agent.tools.findLast(x => x.name === evt.tool && x.status === 'running'); if (t) t.status = evt.is_error ? 'error' : 'done' }
                } else if (evt.type === 'quality_fix_done') {
                  this.syncResult = evt
                  this.fixing = false
                  if (evt.success) await this.checkQuality()
                  return
                }
              } catch(_) {}
            }
          }
        }
      } catch (e) {
        this.syncResult = { success: false, error: e.message }
        this.fixing = false
      }
    },
  }
}).mount('#app')
