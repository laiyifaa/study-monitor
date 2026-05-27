<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './utils/auth'

const auth = useAuthStore()

onMounted(async () => {
  // 如果没有 token，尝试钉钉免登
  if (!auth.token) {
    await auth.tryDingTalkLogin()
  }
})
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f5f7fa; color: #333; }
</style>
