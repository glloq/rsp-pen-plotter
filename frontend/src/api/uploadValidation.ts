// Pre-flight checks every uploader runs before opening a network round-trip.
// Mirrors the backend's contract so we surface the same error the server
// would have returned — but without paying the upload cost.

import { i18n } from '../i18n'

// Must match ``MAX_UPLOAD_BYTES`` in ``backend/pen_plotter/api/upload.py``
// (and ``files.py``). Kept in sync by hand: bumping the backend cap
// requires updating this constant too, otherwise the UI accepts files
// the server will refuse.
export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024

// Accepted file extensions. Same list the ``<input accept>`` attribute
// uses (see useFileManager.FILE_ACCEPT) — duplicated here as a Set so
// drag-and-drop (which bypasses the browser's accept filter) can run the
// same check.
export const ACCEPTED_EXTENSIONS = new Set([
  'svg',
  'png',
  'jpg',
  'jpeg',
  'tiff',
  'webp',
  'heic',
  'pdf',
  'dxf',
  'eps',
  'ps',
  'ai',
  'txt',
  'md',
  'html',
  'docx',
  'odt',
  'rtf',
])

export interface UploadValidationError {
  /** Localised, user-facing reason the upload was rejected. */
  message: string
  /** Stable identifier so callers can branch on the failure type. */
  code: 'empty' | 'tooLarge' | 'invalidType' | 'nameTooLong'
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.')
  if (dot < 0 || dot === name.length - 1) return ''
  return name.slice(dot + 1).toLowerCase()
}

/**
 * Validate a file the user is about to upload. Returns ``null`` when the
 * file passes every check, or a structured error otherwise. The caller
 * is expected to surface ``error.message`` (already localised) to the
 * operator and abort the upload.
 */
export function validateUploadFile(file: File): UploadValidationError | null {
  const t = i18n.global.t
  if (file.size === 0) {
    return { code: 'empty', message: t('upload.emptyFile') }
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      code: 'tooLarge',
      message: t('upload.tooLarge', {
        max: Math.floor(MAX_UPLOAD_BYTES / (1024 * 1024)),
      }),
    }
  }
  // 255 bytes is the POSIX filename ceiling; the backend enforces the
  // same limit. Use byte length (not character count) to match.
  if (new TextEncoder().encode(file.name).length > 255) {
    return { code: 'nameTooLong', message: t('upload.nameTooLong') }
  }
  const ext = extensionOf(file.name)
  if (!ext || !ACCEPTED_EXTENSIONS.has(ext)) {
    return {
      code: 'invalidType',
      message: t('upload.invalidType', { ext: ext || '?' }),
    }
  }
  return null
}
