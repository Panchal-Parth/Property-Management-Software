import { useEffect, useRef, useState } from 'react'
import type { Document } from './types'

export default function DocumentPreview({ file, close }: { file: Document; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    dialog.current?.showModal()
    const controller = new AbortController()
    let objectUrl = ''
    async function load() {
      try {
        if (!['application/pdf', 'image/png', 'image/jpeg'].includes(file.mime)) throw new Error('Preview is unavailable for this file type. Download it to view it.')
        const response = await fetch(`/api/documents/${file.id}/download`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
        if (!response.ok) {
          if (response.status === 401) window.dispatchEvent(new Event('havenly:unauthorized'))
          throw new Error(response.status === 404 ? 'This document is no longer available.' : 'Unable to open this document. Close the preview and try again.')
        }
        const bytes = await response.arrayBuffer()
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(new Blob([bytes], { type: file.mime }))
        setUrl(objectUrl)
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message)
      }
    }
    void load()
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [file.id, file.mime])
  return <dialog ref={dialog} className="document-preview" aria-labelledby="document-preview-title" onCancel={e => { e.preventDefault(); close() }}>
    <div className="modal-head"><h2 id="document-preview-title">{file.filename}</h2><button className="secondary-btn" onClick={close} autoFocus>Close preview</button></div>
    <div className="preview-toolbar"><span>Private document · visible only while signed in</span><a className="text-btn" href={`/api/documents/${file.id}/download`}>Download original</a></div>
    {error ? <p role="alert">{error}</p> : !url ? <p role="status">Loading document…</p> : file.mime === 'application/pdf' ? <><p className="subheading">If your browser cannot display this PDF, use Download original.</p><iframe title={`Preview of ${file.filename}`} src={url} /></> : <div className="preview-image"><img src={url} alt={file.filename} onError={() => setError('The image could not be displayed. Try downloading the original.')} /></div>}
  </dialog>
}
