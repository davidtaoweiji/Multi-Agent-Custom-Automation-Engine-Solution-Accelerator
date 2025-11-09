/**
 * FileUpload Component
 * Multi-file upload component for invoice processing
 * Supports images (jpg, png, etc.) and PDF files
 */

import React, { useState, useRef } from 'react';
import {
  Button,
  makeStyles,
  shorthands,
  tokens,
  Text,
  Card,
  Toast,
  ToastTitle,
  ToastBody,
  Toaster,
  useToastController,
  useId,
} from '@fluentui/react-components';
import {
  Attach24Regular,
  Delete24Regular,
  Image24Regular,
  Document24Regular,
  CheckmarkCircle24Regular,
} from '@fluentui/react-icons';

const useStyles = makeStyles({
  container: {
    display: 'flex',
    flexDirection: 'column',
    ...shorthands.gap('12px'),
    ...shorthands.padding('16px'),
  },
  uploadButton: {
    width: 'fit-content',
  },
  filesContainer: {
    display: 'flex',
    flexWrap: 'wrap',
    ...shorthands.gap('12px'),
  },
  fileCard: {
    position: 'relative',
    width: '120px',
    height: '120px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    ...shorthands.padding('8px'),
  },
  filePreview: {
    width: '100%',
    height: '80px',
    objectFit: 'cover',
    ...shorthands.borderRadius(tokens.borderRadiusMedium),
  },
  pdfIcon: {
    fontSize: '48px',
    color: tokens.colorBrandForeground1,
  },
  fileName: {
    fontSize: '11px',
    marginTop: '4px',
    textAlign: 'center',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    width: '100%',
  },
  deleteButton: {
    position: 'absolute',
    top: '4px',
    right: '4px',
    minWidth: '28px',
    minHeight: '28px',
  },
  fileInput: {
    display: 'none',
  },
  noFiles: {
    color: tokens.colorNeutralForeground3,
    fontStyle: 'italic',
  },
});

export interface UploadedFile {
  file: File;
  preview?: string; // Only for images
  id: string;
  type: 'image' | 'pdf';
}

interface FileUploadProps {
  files: UploadedFile[];
  onFilesChange: (files: UploadedFile[]) => void;
  maxFiles?: number;
  acceptedTypes?: string; // MIME types, e.g., "image/*,.pdf"
}

export const FileUpload: React.FC<FileUploadProps> = ({
  files,
  onFilesChange,
  maxFiles = 5,
  acceptedTypes = 'image/*,.pdf,application/pdf',
}) => {
  const styles = useStyles();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toasterId = useId('file-upload-toaster');
  const { dispatchToast } = useToastController(toasterId);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = event.target.files;
    if (!selectedFiles) return;

    const newFiles: UploadedFile[] = [];
    const currentFiles = files || [];
    const remainingSlots = maxFiles - currentFiles.length;

    for (let i = 0; i < Math.min(selectedFiles.length, remainingSlots); i++) {
      const file = selectedFiles[i];
      
      // Check if file is an image or PDF
      const isImage = file.type.startsWith('image/');
      const isPDF = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');

      if (!isImage && !isPDF) {
        console.warn(`File ${file.name} is not an image or PDF`);
        continue;
      }

      const id = `${Date.now()}-${i}`;
      const uploadedFile: UploadedFile = {
        file,
        id,
        type: isImage ? 'image' : 'pdf',
      };

      // Create preview URL only for images
      if (isImage) {
        uploadedFile.preview = URL.createObjectURL(file);
      }

      newFiles.push(uploadedFile);
    }

    onFilesChange([...currentFiles, ...newFiles]);

    // Show success toast
    if (newFiles.length > 0) {
      const imageUploaded = newFiles.filter(f => f.type === 'image').length;
      const pdfUploaded = newFiles.filter(f => f.type === 'pdf').length;
      
      let message = '';
      if (imageUploaded > 0 && pdfUploaded > 0) {
        message = `${imageUploaded} image${imageUploaded > 1 ? 's' : ''} and ${pdfUploaded} PDF${pdfUploaded > 1 ? 's' : ''} uploaded successfully`;
      } else if (imageUploaded > 0) {
        message = `${imageUploaded} image${imageUploaded > 1 ? 's' : ''} uploaded successfully`;
      } else {
        message = `${pdfUploaded} PDF${pdfUploaded > 1 ? 's' : ''} uploaded successfully`;
      }

      dispatchToast(
        <Toast>
          <ToastTitle action={<CheckmarkCircle24Regular />}>
            Files Uploaded
          </ToastTitle>
          <ToastBody>{message}</ToastBody>
        </Toast>,
        { intent: 'success', timeout: 3000 }
      );
    }

    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleDeleteFile = (fileId: string) => {
    const fileToDelete = files?.find((f) => f.id === fileId);
    if (fileToDelete?.preview) {
      // Revoke object URL to free memory (only for images)
      URL.revokeObjectURL(fileToDelete.preview);
    }

    const updatedFiles = (files || []).filter((f) => f.id !== fileId);
    onFilesChange(updatedFiles);
  };

  // Safely handle files array with default empty array
  const safeFiles = files || [];
  const canUploadMore = safeFiles.length < maxFiles;

  // Count images and PDFs
  const imageCount = safeFiles.filter(f => f.type === 'image').length;
  const pdfCount = safeFiles.filter(f => f.type === 'pdf').length;

  return (
    <div className={styles.container}>
      <Toaster toasterId={toasterId} position="top-end" />
      
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Button
          className={styles.uploadButton}
          appearance="secondary"
          icon={<Attach24Regular />}
          onClick={handleUploadClick}
          disabled={!canUploadMore}
        >
          Attach Files ({safeFiles.length}/{maxFiles})
        </Button>
        {safeFiles.length > 0 && (
          <Text size={200} className={styles.noFiles}>
            {imageCount > 0 && `${imageCount} image${imageCount > 1 ? 's' : ''}`}
            {imageCount > 0 && pdfCount > 0 && ', '}
            {pdfCount > 0 && `${pdfCount} PDF${pdfCount > 1 ? 's' : ''}`}
          </Text>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={acceptedTypes}
        multiple
        className={styles.fileInput}
        onChange={handleFileSelect}
      />

      {safeFiles.length > 0 && (
        <div className={styles.filesContainer}>
          {safeFiles.map((uploadedFile) => (
            <Card key={uploadedFile.id} className={styles.fileCard}>
              <Button
                appearance="subtle"
                icon={<Delete24Regular />}
                size="small"
                className={styles.deleteButton}
                onClick={() => handleDeleteFile(uploadedFile.id)}
                aria-label={`Delete ${uploadedFile.file.name}`}
              />
              
              {uploadedFile.type === 'image' && uploadedFile.preview ? (
                <img
                  src={uploadedFile.preview}
                  alt={uploadedFile.file.name}
                  className={styles.filePreview}
                />
              ) : (
                <Document24Regular className={styles.pdfIcon} />
              )}
              
              <Text className={styles.fileName} title={uploadedFile.file.name}>
                {uploadedFile.file.name}
              </Text>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};

// Keep backward compatibility - export as ImageUpload too
export const ImageUpload = FileUpload;
export type ImageFile = UploadedFile;
