import { defineConfig } from 'astro/config';

// https://astro.build/config
export default defineConfig({
  site: 'https://el-j.github.io',
  base: '/omv-agent-station',
  output: 'static',
  build: {
    format: 'file'
  }
});
