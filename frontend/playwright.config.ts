import { defineConfig, devices } from '@playwright/test';
export default defineConfig({testDir:'./e2e',fullyParallel:true,use:{baseURL:'http://127.0.0.1:4173',trace:'retain-on-failure'},webServer:{command:'npm run preview -- --port 4173',port:4173,reuseExistingServer:true},projects:[{name:'điện thoại',use:{...devices['iPhone 13']}},{name:'máy tính',use:{viewport:{width:1440,height:900}}}]});
