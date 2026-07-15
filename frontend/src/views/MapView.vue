<script setup lang="ts">
import { Map as MapIcon } from "lucide-vue-next";
</script>

<template>
  <section class="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
    <MapIcon class="size-10 text-muted-foreground" aria-hidden="true" />
    <h1 class="text-xl font-semibold">Map</h1>
    <p class="max-w-md text-sm text-muted-foreground">
      The interactive alert map is under construction. It will show all currently
      active CAP alerts colored by severity, with filters and time travel.
    </p>
  </section>
</template>
