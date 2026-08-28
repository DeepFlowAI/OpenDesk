import type {
  LearningMaterialCreatePayload,
  MaterialType,
  MaterialUploadCredentialResponse,
} from '@/models/learning'

export const MATERIAL_EXTENSIONS: Record<MaterialType, string[]> = {
  video: ['mp4', 'mov', 'avi', 'mkv', 'flv'],
  audio: ['mp3', 'wav', 'aac'],
  pdf: ['pdf'],
  document: ['doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'],
}

export const MATERIAL_SIZE_LIMITS: Record<MaterialType, number> = {
  video: 1 * 1024 * 1024 * 1024,
  audio: 100 * 1024 * 1024,
  pdf: 50 * 1024 * 1024,
  document: 50 * 1024 * 1024,
}

export type DetectResult =
  | { ok: true; type: MaterialType }
  | { ok: false; reason: 'format' | 'size' }

export function detectMaterialType(file: File): DetectResult {
  const name = file.name.toLowerCase()
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1) : ''
  for (const type of Object.keys(MATERIAL_EXTENSIONS) as MaterialType[]) {
    if (!MATERIAL_EXTENSIONS[type].includes(ext)) continue
    if (file.size > MATERIAL_SIZE_LIMITS[type]) return { ok: false, reason: 'size' }
    return { ok: true, type }
  }
  return { ok: false, reason: 'format' }
}

/** Read media duration before upload so progress rules work from the start. */
export function readMediaDurationSeconds(file: File): Promise<number | undefined> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const element = document.createElement(file.type.startsWith('audio') ? 'audio' : 'video')
    element.preload = 'metadata'
    element.onloadedmetadata = () => {
      URL.revokeObjectURL(url)
      resolve(Number.isFinite(element.duration) ? Math.round(element.duration) : undefined)
    }
    element.onerror = () => {
      URL.revokeObjectURL(url)
      resolve(undefined)
    }
    element.src = url
  })
}

export type UploadProgressFn = (percent: number) => void

/** Upload to OSS via a presigned PUT URL; XHR is used for upload progress events. */
export function putToPresignedUrl(
  uploadUrl: string,
  file: File,
  onProgress: UploadProgressFn,
  signal: { cancelled: boolean },
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', uploadUrl)
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`Upload failed with status ${xhr.status}`))
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.onabort = () => reject(new Error('Upload cancelled'))
    const timer = setInterval(() => {
      if (signal.cancelled) {
        clearInterval(timer)
        xhr.abort()
      }
    }, 200)
    xhr.onloadend = () => clearInterval(timer)
    xhr.send(file)
  })
}

/** Upload a video straight to Aliyun VOD with the one-time credential. */
export async function uploadToVod(
  credential: MaterialUploadCredentialResponse,
  file: File,
  onProgress: UploadProgressFn,
): Promise<void> {
  const uploadAddress = credential.upload_address ?? ''
  if (uploadAddress.startsWith('mock://')) {
    // Local development with the mock provider: nothing to upload.
    onProgress(100)
    return
  }
  const sdk = (await import('aliyun-upload-vod')).default
  if (!sdk) throw new Error('VOD upload SDK unavailable')
  const uploadAuth = credential.upload_auth ?? ''
  const videoId = credential.video_id ?? ''
  await new Promise<void>((resolve, reject) => {
    const uploader = new sdk.Vod({
      userId: '0',
      partSize: 1048576,
      parallel: 5,
      retryCount: 3,
      retryDuration: 2,
      onUploadstarted: (uploadInfo) => {
        uploader.setUploadAuthAndAddress(uploadInfo, uploadAuth, uploadAddress, videoId)
      },
      onUploadSucceed: () => {
        onProgress(100)
        resolve()
      },
      onUploadFailed: (_info, _code, message) => reject(new Error(message || 'VOD upload failed')),
      onUploadProgress: (_info, totalSize, uploadedSize) => {
        if (totalSize > 0) onProgress(Math.min(99, Math.round((uploadedSize / totalSize) * 100)))
      },
    })
    uploader.addFile(file, null, null, null, JSON.stringify({ Vod: { VideoId: videoId } }))
    uploader.startUpload()
  })
}

export function buildMaterialPayload(
  file: File,
  type: MaterialType,
  credential: MaterialUploadCredentialResponse,
  durationSeconds: number | undefined,
): LearningMaterialCreatePayload {
  const baseName = file.name.replace(/\.[^.]+$/, '')
  return {
    name: baseName.slice(0, 50) || file.name.slice(0, 50),
    type,
    vod_video_id: credential.video_id ?? undefined,
    file_key: credential.file_key ?? undefined,
    file_size: file.size,
    duration_seconds: durationSeconds,
  }
}
