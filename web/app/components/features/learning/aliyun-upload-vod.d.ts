declare module 'aliyun-upload-vod' {
  interface VodUploadInfo {
    file: File
    videoId?: string
    [key: string]: unknown
  }

  interface VodUploaderOptions {
    userId?: string
    region?: string
    partSize?: number
    parallel?: number
    retryCount?: number
    retryDuration?: number
    onUploadstarted?: (uploadInfo: VodUploadInfo) => void
    onUploadSucceed?: (uploadInfo: VodUploadInfo) => void
    onUploadFailed?: (uploadInfo: VodUploadInfo, code: string, message: string) => void
    onUploadProgress?: (uploadInfo: VodUploadInfo, totalSize: number, uploadedSize: number) => void
  }

  interface VodUploader {
    addFile(
      file: File,
      endpoint: string | null,
      bucket: string | null,
      object: string | null,
      paramData: string,
    ): void
    setUploadAuthAndAddress(
      uploadInfo: VodUploadInfo,
      uploadAuth: string,
      uploadAddress: string,
      videoId: string,
    ): void
    startUpload(): void
    cancelFile(index: number): void
    dispose(): void
  }

  interface AliyunUploadModule {
    Vod: new (options: VodUploaderOptions) => VodUploader
  }

  const AliyunUpload: AliyunUploadModule
  export default AliyunUpload
}
