import * as React from 'react'
import * as monaco from 'monaco-editor'
import { useApp } from '../store'

export default function Editor() {
  const containerRef = React.useRef<HTMLDivElement | null>(null)
  const editorRef = React.useRef<monaco.editor.IStandaloneCodeEditor | null>(null)
  const doc = useApp(s => s.document)
  const saveDoc = useApp(s => s.saveDoc)
  const setEditBuffer = useApp(s => s.setEditBuffer)

  React.useEffect(() => {
    if (!containerRef.current) return
    editorRef.current = monaco.editor.create(containerRef.current, {
      value: doc?.content ?? '',
      language: 'markdown',
      automaticLayout: true,
      minimap: { enabled: false },
    })
    const sub = editorRef.current.onDidChangeModelContent(() => {
      const v = editorRef.current?.getValue() ?? ''
      setEditBuffer(v)
    })
    return () => {
      sub.dispose()
      editorRef.current?.dispose()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  React.useEffect(() => {
    if (editorRef.current && doc) {
      const curr = editorRef.current.getValue()
      if (curr !== doc.content) {
        editorRef.current.setValue(doc.content)
      }
    }
  }, [doc])

  const onSave = async () => {
    if (!editorRef.current) return
    const text = editorRef.current.getValue()
    await saveDoc(text)
  }

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <div className="section-title">Document</div>
        <div style={{ marginLeft: 'auto' }}>
          <button className="btn" onClick={onSave}>Save</button>
        </div>
      </div>
      <div className="monaco" ref={containerRef} />
    </div>
  )
}
