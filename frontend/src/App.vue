<script setup lang="ts">
import { RouterView } from "vue-router";

import SideMenu from "@/components/SideMenu.vue";
</script>

<template>
  <div class="flex h-dvh flex-col-reverse bg-background text-foreground md:flex-row">
    <SideMenu />
    <main class="min-h-0 flex-1 overflow-auto pb-16 md:pb-0">
      <RouterView />
    </main>
  </div>
</template>
