<script setup lang="ts">
import { Landmark } from "lucide-vue-next";
</script>

<template>
  <section class="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
    <Landmark class="size-10 text-muted-foreground" aria-hidden="true" />
    <h1 class="text-xl font-semibold">Authorities</h1>
    <p class="max-w-md text-sm text-muted-foreground">
      The list of registered alerting authorities is under construction. It will
      show each authority with its country, website and current alert activity.
    </p>
  </section>
</template>
