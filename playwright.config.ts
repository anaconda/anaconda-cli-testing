/**
 * playwright.config.ts: This module is responsible for configuring the Playwright test runner.
 * It includes settings for test execution, browser configuration, and environment variables.
 * See https://playwright.dev/docs/test-configuration for more details.
 */

import { AnacondaConfigDefaults, AnacondaProjectDefaults } from '@anaconda/playwright-utils';
import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';
dotenv.config({ path: '.env' });
import path from 'path';
import os from 'os';

// Default url for all tests to use allowing to run tests against staging/dev.
export const BASE_URL = process.env.URL || 'https://www.saucedemo.com';
export const STORAGE_STATE_PATH = path.join(__dirname, 'playwright/.auth');
// const customLoggerPath = require.resolve('@anaconda/playwright-utils/custom-logger');
// auth token for API calls
const bearerToken = process.env.BEARER_TOKEN;

export default defineConfig({
  // Setup the defaults for all projects
  ...AnacondaConfigDefaults,
  /**
   * The directory where tests are located.
   * See https://playwright.dev/docs/api/class-testconfig#testconfig-testdir
   */
  testDir: './tests',
  //globalSetup: require.resolve('./test-setup/global-setup'),
  //globalTeardown: require.resolve('./test-setup/global-teardown'),
  use: {
    ...AnacondaProjectDefaults,
    /* Records traces after each test failure for debugging purposes. */
    trace: 'retain-on-failure',
    /* Captures screenshots after each test failure to provide visual context. */
    screenshot: 'only-on-failure',
    headless: true,
    // testIdAttribute: 'qa-target',
    baseURL: BASE_URL,
    /* Sets extra headers for auth token */
    extraHTTPHeaders: {
      Authorization: `Bearer ${bearerToken}`,
    },
  },

  /**
   * Configure projects for major browsers.
   * See https://playwright.dev/docs/test-configuration#projects
   */
  projects: [
    {
      name: 'setup',
      testMatch: '**/login-storage-setup.ts',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1600, height: 1000 },
        launchOptions: {
          args: ['--disable-web-security'],
          slowMo: 0,
        },
      },
    },

    /** Due to different view ports in Head and Headless, created 2 projects one for head mode and the same browser for headless. */
    {
      name: 'chromium',
      // dependencies: ['setup'],
      use: {
        viewport: null,
        // Set the storage state here if you have only one user to login.
        // storageState: STORAGE_STATE_LOGIN,
        launchOptions: {
          args: ['--disable-web-security', '--start-maximized'],
          /* --auto-open-devtools-for-tabs option is used to open a test with Network tab for debugging. It can help in analyzing network requests and responses.*/
          // args: ["--auto-open-devtools-for-tabs"],
          // channel: 'chrome',
          slowMo: 0,
          headless: false,
        },
      },
    },

    {
      name: 'chromiumheadless',
      // dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1600, height: 1000 },
        // storageState: STORAGE_STATE_LOGIN,
        launchOptions: {
          args: ['--disable-web-security'],
          // channel: 'chrome',
          slowMo: 0,
          headless: true,
        },
      },
    },

    // Due to different prod setup using a different project
    {
      name: 'chromiumProd',
      // dependencies: ['setup'],
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1600, height: 1000 },
        // storageState: STORAGE_STATE_LOGIN,
        launchOptions: {
          args: ['--disable-web-security'],
          // channel: 'chrome',
          slowMo: 0,
          headless: true,
        },
      },
    },

    /******* Uncomment to run tests in other browsers
    {
      name: 'firefox',
      use: {
        ...devices['Desktop Firefox'],
        viewport: { width: 1600, height: 1000 },
        launchOptions: {
          firefoxUserPrefs: {
            'browser.cache.disk.enable': false,
            'browser.cache.memory.enable': false,
          },
        },
      },
    },

    {
      name: 'webkit',
      use: {
        ...devices['Desktop Safari'],
        viewport: { width: 1600, height: 1000 },
      },
    },

    // Test against mobile viewports.
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },

    // Test against branded browsers.
    {
      name: 'Microsoft Edge',
      use: { ...devices['Desktop Edge'], channel: 'msedge' },
    },
    {
      name: 'Google Chrome',
      use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    },

  ***************/
  ],

  /**
   * If the tests are being run on localhost, this configuration starts a web server.
   * See https://playwright.dev/docs/test-webserver#configuring-a-web-server
   */
  webServer: {
    cwd: `${os.homedir()}/repos/ui`, // You can also use the relative path to the UI repo
    command: 'npm start ui-server', // Start the UI server
    url: BASE_URL,
    ignoreHTTPSErrors: true,
    timeout: 2 * 60 * 1000,
    reuseExistingServer: true,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
