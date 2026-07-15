<script setup lang="ts">
import { SEVERITIES } from "@/lib/severity";
</script>

<template>
  <div
    class="pointer-events-auto rounded-md border border-border bg-card/90 px-3 py-2 shadow-sm backdrop-blur"
    role="group"
    aria-label="Alert severity legend"
  >
    <ul class="flex flex-col gap-1.5">
      <li
        v-for="severity in SEVERITIES"
        :key="severity.value"
        :data-severity="severity.value"
        class="flex items-center gap-2 text-xs text-foreground"
      >
        <span
          class="legend-swatch inline-block size-3 rounded-sm"
          :style="{ backgroundColor: severity.color }"
          aria-hidden="true"
        ></span>
        {{ severity.label }}
      </li>
    </ul>
  </div>
</template>
