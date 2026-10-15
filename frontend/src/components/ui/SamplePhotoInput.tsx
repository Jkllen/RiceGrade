import { useEffect, useRef, useState } from 'react';

const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

type Props = {
  onPhoto: (file: File) => void | Promise<void>;
  disabled?: boolean;
  busy?: boolean;
  title?: string;
};

/** Both upload and camera capture ultimately hand the same File to the existing R2 upload flow. */
export function SamplePhotoInput({ onPhoto, disabled = false, busy = false, title }: Props) {
  const uploadRef = useRef<HTMLInputElement>(null);
  const nativeCameraRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraBusy, setCameraBusy] = useState(false);
  const [error, setError] = useState('');

  function stopCamera() {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOpen(false);
  }

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => {
    if (cameraOpen && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      void videoRef.current.play().catch(() => setError('Camera preview could not start. Try Take photo instead.'));
    }
  }, [cameraOpen]);

  function chooseFile(file?: File) {
    if (!file) return;
    if (!IMAGE_TYPES.has(file.type)) {
      setError('Please choose or capture a JPEG, PNG, or WebP image.');
      return;
    }
    if (!file.size || file.size > MAX_IMAGE_BYTES) {
      setError('Image must be at most 5 MB. Try a lower-resolution photo or retake it.');
      return;
    }
    setError('');
    stopCamera();
    void Promise.resolve(onPhoto(file)).catch(() => setError('Unable to accept the image. Please try again.'));
  }

  async function openCamera() {
    if (disabled || cameraBusy) return;
    setError('');
    if (!navigator.mediaDevices?.getUserMedia) {
      // Native file capture is a graceful fallback for unsupported browsers.
      nativeCameraRef.current?.click();
      return;
    }
    setCameraBusy(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      });
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = stream;
      setCameraOpen(true);
    } catch {
      setError('Camera access was denied or unavailable. Use Take photo (phone camera) or upload a saved photo.');
    } finally {
      setCameraBusy(false);
    }
  }

  async function takeSnapshot() {
    const video = videoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError('Camera is still starting. Wait until you see the rice sample.');
      return;
    }
    setCameraBusy(true);
    try {
      const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Cannot capture camera frame');
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.88));
      if (!blob) throw new Error('Camera could not create a JPEG photo');
      chooseFile(new File([blob], `ricegrade-camera-${Date.now()}.jpg`, { type: 'image/jpeg' }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to capture the photo.');
    } finally {
      setCameraBusy(false);
    }
  }

  return <div className="sample-photo-input">
    {title && <strong className="sample-photo-title">{title}</strong>}
    <div className="sample-photo-actions">
      <button type="button" className="button button-secondary" disabled={disabled || busy} onClick={() => uploadRef.current?.click()}>Upload existing photo</button>
      <button type="button" className="button button-secondary" disabled={disabled || busy || cameraBusy} onClick={() => nativeCameraRef.current?.click()}>Take photo (phone camera)</button>
      <button type="button" className="button button-secondary" disabled={disabled || busy || cameraBusy} onClick={() => void openCamera()}>Live camera preview</button>
    </div>
    <input ref={uploadRef} className="visually-hidden-file" aria-label="Upload existing rice photo" type="file" accept="image/jpeg,image/png,image/webp" disabled={disabled || busy} onChange={e => { chooseFile(e.target.files?.[0]); e.target.value = ''; }}/>
    <input ref={nativeCameraRef} className="visually-hidden-file" aria-label="Take rice photo with phone" type="file" accept="image/*" capture="environment" disabled={disabled || busy} onChange={e => { chooseFile(e.target.files?.[0]); e.target.value = ''; }}/>
    {cameraOpen && <div className="camera-preview-panel">
      <video ref={videoRef} autoPlay playsInline muted aria-label="Live rice sample camera preview" />
      <p>Position separated milled-rice grains on a dark, even background. The camera stays local until you capture a photo.</p>
      <div className="sample-photo-actions">
        <button type="button" className="button button-primary" disabled={cameraBusy || disabled || busy} onClick={() => void takeSnapshot()}>{cameraBusy ? 'Capturing…' : 'Capture photo'}</button>
        <button type="button" className="button button-secondary" onClick={stopCamera}>Close camera</button>
      </div>
    </div>}
    {error && <p className="sample-photo-error" role="alert">{error}</p>}
    <small className="muted">JPEG, PNG or WebP · up to 5 MB · use your phone's rear camera when available.</small>
  </div>;
}
