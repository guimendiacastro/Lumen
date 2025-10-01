import { useApp } from '../store'
import { useEffect } from 'react'

export default function Chat() {
  const ready = useApp(s => s.ready)
  const error = useApp(s => s.error)
  const init = useApp(s => s.init)
  const createDoc = useApp(s => s.createDocumentAndThread)
  const input = useApp(s => s.input)
  const setInput = useApp(s => s.setInput)
  const askAI = useApp(s => s.askAI)
  const doc = useApp(s => s.document)

  useEffect(() => {
    (async () => {
      await init()
      await createDoc()
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (error) return <div className="mini" style={{ color: 'crimson' }}>Error: {error}</div>
  if (!ready || !doc) return <div className="mini">Loading…</div>

  return (
    <div>
      <div className="section-title">Chat</div>
      <div className="row" style={{ gap: 8 }}>
        <input
          className="input"
          placeholder="Ask something about your document / draft a clause…"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') askAI() }}
        />
        <button className="btn primary" onClick={askAI}>Ask</button>
      </div>
      <div className="mini" style={{ marginTop: 8 }}>
        New doc created: <strong>{doc.title}</strong>
      </div>
    </div>
  )
}
