import '@testing-library/jest-dom/vitest';
if (!URL.createObjectURL) URL.createObjectURL = () => 'blob:kiem-thu';
if (!URL.revokeObjectURL) URL.revokeObjectURL = () => undefined;
