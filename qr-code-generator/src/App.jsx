import React, { useState, useRef, useEffect } from 'react'
import QRCode from 'qrcode'

export default function App() {
  const [text, setText] = useState('https://example.com')
  const [size, setSize] = useState(256)
  const [fgColor, setFgColor] = useState('#000000')
  const [bgColor, setBgColor] = useState('#ffffff')
  const [errorLevel, setErrorLevel] = useState('M')
  const canvasRef = useRef(null)

  useEffect(() => {
    generate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, size, fgColor, bgColor, errorLevel])

  async function generate() {
    const canvas = canvasRef.current
    if (!canvas) return
    try {
      await QRCode.toCanvas(canvas, text || ' ', {
        width: size,
        color: {
          dark: fgColor,
          light: bgColor,
        },
        errorCorrectionLevel: errorLevel,
      })
    } catch (err) {
      console.error('QR generation failed', err)
    }
  }

  function downloadPNG() {
    const canvas = canvasRef.current
    if (!canvas) return
    const url = canvas.toDataURL('image/png')
    const a = document.createElement('a')
    a.href = url
    a.download = 'qrcode.png'
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return (
    <div className="container">
      <h1>QR Code Generator</h1>
      <div className="grid">
        <div className="controls">
          <label>
            Text/URL
            <textarea aria-label="QR text" value={text} onChange={(e) => setText(e.target.value)} />
          </label>

          <label>
            Size: {size}px
            <input aria-label="QR size" type="range" min="64" max="1024" value={size} onChange={(e) => setSize(Number(e.target.value))} />
          </label>

          <label>
            Foreground
            <input aria-label="Foreground color" type="color" value={fgColor} onChange={(e) => setFgColor(e.target.value)} />
          </label>

          <label>
            Background
            <input aria-label="Background color" type="color" value={bgColor} onChange={(e) => setBgColor(e.target.value)} />
          </label>

          <label>
            Error Correction
            <select value={errorLevel} onChange={(e) => setErrorLevel(e.target.value)}>
              <option value="L">L - Low</option>
              <option value="M">M - Medium</option>
              <option value="Q">Q - Quartile</option>
              <option value="H">H - High</option>
            </select>
          </label>

          <div className="buttons">
            <button onClick={generate}>Refresh</button>
            <button onClick={downloadPNG}>Download PNG</button>
          </div>
        </div>

        <div className="preview">
          <h2>Preview</h2>
          <div className="canvasWrap">
            <canvas ref={canvasRef} width={size} height={size} />
          </div>
        </div>
      </div>

      <footer>
        <small>Client-side QR generation — no server required.</small>
      </footer>
    </div>
  )
}
