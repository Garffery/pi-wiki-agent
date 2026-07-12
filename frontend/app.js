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
      showAddProject: false,
      newProject: { name: '', path: '' },
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
    }
  },

  async mounted() {
    await this.checkHealth()
    await Promise.all([this.loadProjects(), this.loadModels()])
  },

  methods: {
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
      this.currentView = 'commits'
      await Promise.all([this.refreshCommits(), this.loadFilters()])
    },

    async refreshCommits() {
      if (!this.selectedProject) return
      this.loading = true
      try { const r = await fetch(`${API}/projects/${this.selectedProject}/commits`); this.commits = await r.json() } catch (e) { console.error(e) }
      this.loading = false
    },

    async previewCommit(rev) {
      this.selectedCommit = rev; this.syncResult = null
      try { const r = await fetch(`${API}/projects/${this.selectedProject}/commits/${rev}`); this.commitDetail = await r.json() } catch (e) { console.error(e) }
    },

    async syncCommit(rev) {
      this.syncing = true; this.syncResult = null; this.streamText = ''; this.streamTools = []
      await this._syncStream(rev)
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

    async _syncStream(rev) {
      const body = this.selectedModel ? JSON.stringify({ model: this.selectedModel }) : undefined
      try {
        const r = await fetch(`${API}/projects/${this.selectedProject}/sync/${rev}/stream`, {
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

    async addProject() {
      this.addError = ''
      try {
        const r = await fetch(`${API}/projects`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newProject),
        })
        if (r.ok) { this.showAddProject = false; this.newProject = { name: '', path: '' }; await this.loadProjects() }
        else { const err = await r.json(); this.addError = err.detail || '添加失败' }
      } catch (e) { this.addError = e.message }
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
  }
}).mount('#app')
