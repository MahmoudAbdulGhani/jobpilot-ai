import { defineConfig } from '@playwright/test';
export default defineConfig({ testDir:'./tests/e2e', workers:1, fullyParallel:false, timeout:120_000, use:{baseURL:'http://localhost:3000',browserName:'chromium',headless:true,trace:'retain-on-failure'} });
