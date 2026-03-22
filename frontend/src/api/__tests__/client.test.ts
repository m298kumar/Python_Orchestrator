import { describe, it, expect, vi } from 'vitest';

vi.mock('axios', () => {
  const instance = {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    interceptors: {
      response: { use: vi.fn() },
      request: { use: vi.fn() },
    },
  };
  return {
    default: { create: vi.fn(() => instance), ...instance },
  };
});

import {
  triggerPipelineRun,
  listPipelineRuns,
  listAgents,
  uploadRequirements,
  listTestCases,
  listFeatures,
  getHealth,
  getSiteModel,
} from '../client';

describe('API client', () => {
  it('triggerPipelineRun is a function', () => {
    expect(typeof triggerPipelineRun).toBe('function');
  });

  it('listPipelineRuns is a function', () => {
    expect(typeof listPipelineRuns).toBe('function');
  });

  it('listAgents is a function', () => {
    expect(typeof listAgents).toBe('function');
  });

  it('uploadRequirements is a function', () => {
    expect(typeof uploadRequirements).toBe('function');
  });

  it('listTestCases is a function', () => {
    expect(typeof listTestCases).toBe('function');
  });

  it('listFeatures is a function', () => {
    expect(typeof listFeatures).toBe('function');
  });

  it('getHealth is a function', () => {
    expect(typeof getHealth).toBe('function');
  });

  it('getSiteModel is a function', () => {
    expect(typeof getSiteModel).toBe('function');
  });
});
