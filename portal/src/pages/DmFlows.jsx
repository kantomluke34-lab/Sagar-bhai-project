import '@xyflow/react/dist/style.css'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import {
  Archive,
  Bot,
  CheckCircle2,
  Clock3,
  Copy,
  GitBranch,
  Hand,
  Loader2,
  MessageSquareReply,
  MousePointerClick,
  Play,
  Plus,
  Save,
  Send,
  Split,
  Square,
  Trash2,
  UserRoundPen,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../api'
import { PageTitle, Status } from './Dashboard'

const nodeCatalog = [
  ['reply_router', 'Reply router', MessageSquareReply],
  ['wait_reply', 'Wait for reply', MousePointerClick],
  ['send_text', 'Send text', Send],
  ['send_buttons', 'Send buttons', Split],
  ['condition', 'Condition', GitBranch],
  ['delay', 'Delay', Clock3],
  ['update_contact', 'Update contact', UserRoundPen],
  ['handoff', 'Human handoff', Hand],
  ['end', 'End', Square],
]

const labels = Object.fromEntries([['start', 'Campaign entry'], ...nodeCatalog.map(([type, label]) => [type, label])])
const icons = Object.fromEntries([['start', Play], ...nodeCatalog.map(([type, , Icon]) => [type, Icon])])

const blankGraph = () => ({
  nodes: [
    { id: 'start', type: 'start', position: { x: 80, y: 60 }, config: {} },
    { id: 'reply', type: 'reply_router', position: { x: 80, y: 230 }, config: { choices: [{ key: 'yes', label: 'Yes', aliases: ['yes', 'y'] }, { key: 'no', label: 'No', aliases: ['no', 'n'] }] } },
    { id: 'yes_end', type: 'end', position: { x: -60, y: 440 }, config: {} },
    { id: 'no_end', type: 'end', position: { x: 240, y: 440 }, config: {} },
  ],
  edges: [
    { id: 'start_reply', source: 'start', target: 'reply', source_handle: 'default' },
    { id: 'reply_yes', source: 'reply', target: 'yes_end', source_handle: 'yes' },
    { id: 'reply_no', source: 'reply', target: 'no_end', source_handle: 'no' },
  ],
})

function defaultConfig(type) {
  if (type === 'reply_router') return { choices: [{ key: 'yes', label: 'Yes', aliases: ['yes'] }, { key: 'no', label: 'No', aliases: ['no'] }] }
  if (type === 'wait_reply') return {}
  if (type === 'send_text') return { text: 'Thanks for replying, {{name}}.' }
  if (type === 'send_buttons') return { text: 'Choose an option:', choices: [{ key: 'continue', label: 'Continue', aliases: ['continue'] }] }
  if (type === 'condition') return { field: 'last_reply_choice', operator: 'equals', value: 'yes' }
  if (type === 'delay') return { minutes: 5 }
  if (type === 'update_contact') return { field: 'lead_stage', value: 'qualified' }
  if (type === 'handoff') return { reason: 'Customer requested help' }
  return {}
}

function outputHandles(stepType, config) {
  if (['end', 'handoff'].includes(stepType)) return []
  if (['reply_router', 'send_buttons'].includes(stepType)) {
    return [...(config.choices || []).map((choice) => ({ id: choice.key, label: choice.label })), { id: 'fallback', label: 'Other' }, ...(config.timeout_minutes ? [{ id: 'timeout', label: 'Timeout' }] : [])]
  }
  if (stepType === 'wait_reply') return [{ id: 'reply', label: 'Reply' }, ...(config.timeout_minutes ? [{ id: 'timeout', label: 'Timeout' }] : [])]
  if (stepType === 'condition') return [{ id: 'true', label: 'Yes' }, { id: 'false', label: 'No' }]
  return [{ id: 'default', label: '' }]
}

function FlowStepNode({ data, selected }) {
  const Icon = icons[data.stepType] || Bot
  const handles = outputHandles(data.stepType, data.config || {})
  return <div className={`flow-node ${selected ? 'selected' : ''}`}>
    {data.stepType !== 'start' && <Handle type="target" position={Position.Top} />}
    <span className="flow-node-icon"><Icon size={16} /></span>
    <span><strong>{labels[data.stepType]}</strong><small>{summary(data.stepType, data.config || {})}</small></span>
    {!!handles.length && <div className="flow-node-outputs">{handles.map((handle, index) => <span key={handle.id} style={{ left: `${((index + 1) / (handles.length + 1)) * 100}%` }}><em>{handle.label}</em><Handle id={handle.id} type="source" position={Position.Bottom} /></span>)}</div>}
  </div>
}

function summary(type, config) {
  if (type === 'reply_router') return `${config.choices?.length || 0} reply branches`
  if (type === 'wait_reply') return config.timeout_minutes ? `${config.timeout_minutes} min timeout` : 'No timeout'
  if (type === 'send_text' || type === 'send_buttons') return config.text || 'Write a message'
  if (type === 'condition') return `${config.field || 'variable'} ${config.operator || 'equals'} ${config.value || ''}`
  if (type === 'delay') return `${config.minutes || 0} minutes`
  if (type === 'update_contact') return `${config.field || 'field'} = ${config.value || ''}`
  if (type === 'handoff') return config.reason || 'Pause automation'
  if (type === 'start') return 'After the campaign message'
  return 'Complete execution'
}

const nodeTypes = { flowStep: FlowStepNode }

function toCanvas(graph) {
  return {
    nodes: graph.nodes.map((node) => ({ id: node.id, type: 'flowStep', position: node.position, deletable: node.type !== 'start', data: { stepType: node.type, config: node.config || {} } })),
    edges: graph.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, sourceHandle: edge.source_handle || 'default', markerEnd: { type: MarkerType.ArrowClosed } })),
  }
}

function fromCanvas(nodes, edges) {
  return {
    nodes: nodes.map((node) => ({ id: node.id, type: node.data.stepType, position: node.position, config: node.data.config || {} })),
    edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, source_handle: edge.sourceHandle || 'default' })),
  }
}

function editorSnapshot(flow, graph) {
  function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical)
    if (value && typeof value === 'object') {
      return Object.fromEntries(
        Object.keys(value).sort().map((key) => [key, canonical(value[key])]),
      )
    }
    return value
  }
  return JSON.stringify(canonical({
    name: flow.name || '',
    description: flow.description || '',
    graph,
  }))
}

export default function DmFlows() {
  const [flows, setFlows] = useState([])
  const [draft, setDraft] = useState(null)
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [savedSnapshot, setSavedSnapshot] = useState('')

  const selected = nodes.find((node) => node.id === selectedId)
  const executions = draft?.executions || []
  const currentSnapshot = useMemo(
    () => draft ? editorSnapshot(draft, fromCanvas(nodes, edges)) : '',
    [draft, nodes, edges],
  )
  const hasUnsavedChanges = Boolean(draft && currentSnapshot !== savedSnapshot)

  async function load() {
    setLoading(true); setError('')
    try { const { data } = await api.get('/api/dm-flows'); setFlows(data) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'DM flows could not be loaded.') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  function loadCanvas(flow) {
    const canvas = toCanvas(flow.draft_graph)
    setNodes(canvas.nodes); setEdges(canvas.edges); setSelectedId(null)
    setSavedSnapshot(editorSnapshot(flow, flow.draft_graph))
  }

  async function open(flow) {
    setBusy(true); setError(''); setNotice('')
    try { const { data } = await api.get(`/api/dm-flows/${flow.id}`); setDraft(data); loadCanvas(data) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'DM flow could not be opened.') }
    finally { setBusy(false) }
  }

  function startNew() {
    const graph = blankGraph()
    setDraft({ name: 'New campaign flow', description: '', draft_version: 1, draft_graph: graph, status: 'draft' })
    loadCanvas({ draft_graph: graph })
    setError(''); setNotice('')
  }

  function closeEditor() {
    if (hasUnsavedChanges && !window.confirm('Discard unsaved DM flow changes?')) return
    setDraft(null)
  }

  useEffect(() => {
    if (!hasUnsavedChanges) return undefined
    const warnBeforeUnload = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [hasUnsavedChanges])

  const onConnect = useCallback((connection) => {
    setEdges((current) => addEdge({ ...connection, id: `e_${crypto.randomUUID()}`, markerEnd: { type: MarkerType.ArrowClosed } }, current.filter((edge) => !(edge.source === connection.source && (edge.sourceHandle || 'default') === (connection.sourceHandle || 'default')))))
  }, [setEdges])

  function addNode(type) {
    const id = `n_${crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`
    setNodes((current) => [...current, { id, type: 'flowStep', position: { x: 140 + (current.length % 3) * 230, y: 150 + current.length * 45 }, data: { stepType: type, config: defaultConfig(type) } }])
    setSelectedId(id)
  }

  function changeConfig(partial) {
    if (partial.choices && selected) {
      const validHandles = new Set(partial.choices.map((choice) => choice.key))
      validHandles.add('fallback')
      validHandles.add('timeout')
      setEdges((current) => current.filter((edge) => edge.source !== selectedId || validHandles.has(edge.sourceHandle || 'default')))
    }
    setNodes((current) => current.map((node) => node.id === selectedId ? { ...node, data: { ...node.data, config: { ...node.data.config, ...partial } } } : node))
  }

  function removeSelected() {
    if (!selected || selected.data.stepType === 'start') return
    setNodes((current) => current.filter((node) => node.id !== selected.id))
    setEdges((current) => current.filter((edge) => edge.source !== selected.id && edge.target !== selected.id))
    setSelectedId(null)
  }

  async function save() {
    if (draft.name.trim().length < 2) {
      setError('Enter a flow name with at least two characters.')
      setNotice('')
      return null
    }
    setBusy(true); setError(''); setNotice('')
    const graph = fromCanvas(nodes, edges)
    try {
      await api.post('/api/dm-flows/validate', graph)
      const payload = { name: draft.name.trim(), description: draft.description.trim(), graph }
      const response = draft.id
        ? await api.put(`/api/dm-flows/${draft.id}`, { ...payload, expected_version: draft.draft_version })
        : await api.post('/api/dm-flows', payload)
      const { data } = await api.get(`/api/dm-flows/${response.data.id}`)
      setDraft(data); loadCanvas(data); setNotice('Draft saved.'); await load()
      return data
    } catch (requestError) {
      const detail = requestError.response?.data?.detail
      setError(Array.isArray(detail) ? detail.map((item) => item.msg).join(' ') : detail || 'DM flow could not be saved.')
      return null
    } finally { setBusy(false) }
  }

  async function publish() {
    const saved = await save()
    if (!saved) return
    setBusy(true); setError(''); setNotice('')
    try {
      await api.post(`/api/dm-flows/${saved.id}/publish`, { expected_version: saved.draft_version })
      const { data } = await api.get(`/api/dm-flows/${saved.id}`)
      setDraft(data); loadCanvas(data); setNotice(`Version ${data.published_version?.version} published.`); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || 'DM flow could not be published.') }
    finally { setBusy(false) }
  }

  async function duplicate(flow) {
    setBusy(true); setError('')
    try { const { data } = await api.post(`/api/dm-flows/${flow.id}/duplicate`); await load(); await open(data) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'DM flow could not be duplicated.') }
    finally { setBusy(false) }
  }

  async function archive() {
    if (!draft?.id) return
    if (!window.confirm('Archive this DM flow? Scheduled campaigns keep their pinned version.')) return
    setBusy(true); setError('')
    try { await api.post(`/api/dm-flows/${draft.id}/archive`, { expected_version: draft.draft_version }); setDraft(null); await load(); setNotice('DM flow archived.') }
    catch (requestError) { setError(requestError.response?.data?.detail || 'DM flow could not be archived.') }
    finally { setBusy(false) }
  }

  if (draft) return <div className="dm-flow-workspace">
    <header className="flow-toolbar">
      <button className="icon-button" aria-label="Close editor" onClick={closeEditor}><X /></button>
      <div className="flow-title-fields"><input aria-label="Flow name" required minLength="2" value={draft.name} maxLength="160" onChange={(event) => setDraft({ ...draft, name: event.target.value })} /><input aria-label="Flow description" value={draft.description || ''} maxLength="1000" placeholder="What this flow does" onChange={(event) => setDraft({ ...draft, description: event.target.value })} /></div>
      <Status value={draft.status} />
      {hasUnsavedChanges && <span className="flow-unsaved" role="status">Unsaved changes</span>}
      {draft.id && <button className="secondary-button" disabled={busy} onClick={archive}><Archive size={15} />Archive</button>}
      <button className="secondary-button" disabled={busy} onClick={save}><Save size={15} />Save draft</button>
      <button className="primary-button" disabled={busy} onClick={publish}><CheckCircle2 size={15} />Publish</button>
    </header>
    {error && <div className="alert error flow-alert">{error}</div>}{notice && <div className="alert success flow-alert">{notice}</div>}
    <div className="flow-builder">
      <aside className="flow-palette"><span className="eyebrow">FLOW COMPONENTS</span><p>Add a step, then connect its branch handle to the next step.</p>{nodeCatalog.map(([type, label, Icon]) => <button key={type} onClick={() => addNode(type)}><Icon size={16} /><span>{label}</span><Plus size={13} /></button>)}</aside>
      <main className="flow-canvas"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onConnect={onConnect} onNodeClick={(_, node) => setSelectedId(node.id)} onPaneClick={() => setSelectedId(null)} fitView><Background gap={18} size={1} /><MiniMap pannable zoomable /><Controls /></ReactFlow></main>
      <aside className="flow-inspector">{selected ? <NodeInspector node={selected} change={changeConfig} remove={removeSelected} /> : <><span className="eyebrow">STEP SETTINGS</span><div className="empty compact"><MousePointerClick size={24} /><p>Select a step to edit its message, choices, condition, or timeout.</p></div>{draft.id && <ExecutionSummary executions={executions} />}</>}</aside>
    </div>
  </div>

  return <>
    <PageTitle kicker="WHATSAPP AUTOMATION" title="DM Flows" subtitle="Build campaign-specific reply journeys that run before the general CAM assistant." action={<button className="primary-button" onClick={startNew}><Plus size={16} />New DM Flow</button>} />
    {error && <div className="alert error">{error}</div>}{notice && <div className="alert success">{notice}</div>}
    {loading ? <section className="panel empty"><Loader2 className="spin" />Loading DM flows…</section> : flows.length ? <section className="flow-list">{flows.map((flow) => <article key={flow.id} className="flow-card"><div className="flow-card-icon"><Bot /></div><div><span className="eyebrow">{flow.published_version ? `VERSION ${flow.published_version.version}` : 'DRAFT'}</span><h2>{flow.name}</h2><p>{flow.description || 'Campaign-specific WhatsApp reply flow.'}</p><small>Updated {new Date(flow.updated_at).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</small></div><Status value={flow.status} /><div className="flow-card-actions"><button className="secondary-button compact" onClick={() => duplicate(flow)}><Copy size={14} />Duplicate</button><button className="primary-button compact" onClick={() => open(flow)}>Open flow</button></div></article>)}</section> : <section className="panel empty"><Bot size={32} /><h2>No DM flows yet</h2><p>Create a flow, connect each branch, then publish it for campaign use.</p><button className="primary-button" onClick={startNew}><Plus size={16} />Create first flow</button></section>}
  </>
}

function NodeInspector({ node, change, remove }) {
  const type = node.data.stepType
  const config = node.data.config || {}
  const choices = config.choices || []
  function updateChoice(index, partial) { change({ choices: choices.map((choice, current) => current === index ? { ...choice, ...partial } : choice) }) }
  function addChoice() {
    const number = choices.length + 1
    change({ choices: [...choices, { key: `choice_${number}`, label: `Choice ${number}`, aliases: [`choice ${number}`] }] })
  }
  return <><div className="inspector-head"><div><span className="eyebrow">STEP SETTINGS</span><h3>{labels[type]}</h3></div>{type !== 'start' && <button className="icon-button danger" aria-label="Delete step" onClick={remove}><Trash2 /></button>}</div>
    {['send_text', 'send_buttons'].includes(type) && <label>Message<textarea rows="6" maxLength={type === 'send_buttons' ? 1024 : 4096} value={config.text || ''} onChange={(event) => change({ text: event.target.value })} /></label>}
    {['reply_router', 'send_buttons'].includes(type) && <div className="choice-editor"><strong>Reply choices</strong>{choices.map((choice, index) => <div key={choice.key} className="choice-row"><span>{choice.key}</span><input aria-label={`Choice ${index + 1} label`} maxLength="20" value={choice.label} onChange={(event) => updateChoice(index, { label: event.target.value })} /><input aria-label={`Choice ${index + 1} aliases`} value={(choice.aliases || []).join(', ')} onChange={(event) => updateChoice(index, { aliases: event.target.value.split(',').map((value) => value.trim()).filter(Boolean) })} placeholder="yes, y" />{choices.length > 1 && <button className="icon-button" aria-label={`Remove ${choice.label}`} onClick={() => change({ choices: choices.filter((_, current) => current !== index) })}><X /></button>}</div>)}{choices.length < 3 && <button className="secondary-button compact" onClick={addChoice}><Plus size={13} />Add choice</button>}<small>Connect every choice handle. The optional Other handle is the fallback.</small></div>}
    {['reply_router', 'send_buttons', 'wait_reply'].includes(type) && <label>Timeout minutes <small>Leave empty for no timeout.</small><input type="number" min="1" max="10080" value={config.timeout_minutes || ''} onChange={(event) => change({ timeout_minutes: event.target.value ? Number(event.target.value) : undefined })} /></label>}
    {type === 'condition' && <><label>Variable<input value={config.field || ''} onChange={(event) => change({ field: event.target.value })} placeholder="last_reply_choice" /></label><label>Operator<select value={config.operator || 'equals'} onChange={(event) => change({ operator: event.target.value })}><option value="equals">Equals</option><option value="not_equals">Does not equal</option><option value="contains">Contains</option><option value="exists">Exists</option></select></label>{config.operator !== 'exists' && <label>Value<input value={config.value || ''} onChange={(event) => change({ value: event.target.value })} /></label>}</>}
    {type === 'delay' && <label>Delay in minutes<input type="number" min="1" max="10080" value={config.minutes || 1} onChange={(event) => change({ minutes: Number(event.target.value) })} /></label>}
    {type === 'update_contact' && <><label>Contact field<select value={config.field || 'lead_stage'} onChange={(event) => change({ field: event.target.value })}>{['name', 'email', 'company', 'designation', 'city', 'lead_stage', 'notes'].map((field) => <option key={field}>{field}</option>)}</select></label><label>Value<input value={config.value || ''} onChange={(event) => change({ value: event.target.value })} placeholder="Use {{last_reply}} for captured text" /></label></>}
    {type === 'handoff' && <label>Handoff reason<input value={config.reason || ''} onChange={(event) => change({ reason: event.target.value })} /></label>}
    {type === 'start' && <p className="muted">This step runs after Meta accepts the campaign message. It cannot be removed.</p>}
    {type === 'end' && <p className="muted">The execution completes when it reaches this step.</p>}
  </>
}

function ExecutionSummary({ executions }) {
  const totals = useMemo(() => executions.reduce((result, execution) => ({ ...result, [execution.status]: (result[execution.status] || 0) + 1 }), {}), [executions])
  return <div className="execution-summary"><strong>Recent executions</strong>{executions.length ? <><div className="execution-totals">{Object.entries(totals).map(([status, count]) => <span key={status}><Status value={status} />{count}</span>)}</div><div className="execution-recent">{executions.slice(0, 8).map((execution) => <div key={execution.id}><span>{execution.phone}</span><small>{execution.current_node_id}</small><Status value={execution.status} /></div>)}</div></> : <small>No campaign has run this flow yet.</small>}</div>
}
