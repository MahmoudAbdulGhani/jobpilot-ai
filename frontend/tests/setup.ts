import { afterEach, beforeEach } from 'vitest';
import { cleanup } from '@testing-library/react';

beforeEach(() => {
  if (!HTMLDialogElement.prototype.showModal) {
    (HTMLDialogElement.prototype as unknown as { showModal: () => void }).showModal = function () { (this as HTMLDialogElement).open = true; };
    (HTMLDialogElement.prototype as unknown as { close: () => void }).close = function () { (this as HTMLDialogElement).open = false; };
  }
  if (typeof URL.createObjectURL !== 'function') {
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = () => 'blob:stub';
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = () => undefined;
  }
});

afterEach(() => {
  cleanup();
});