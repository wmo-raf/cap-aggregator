<script setup lang="ts">
import { BASEMAPS, type BasemapId } from "@/lib/basemap";

defineProps<{ active: BasemapId }>();
const emit = defineEmits<{ select: [id: BasemapId] }>();
</script>

<template>
  <div
    class="pointer-events-auto flex overflow-hidden rounded-md border border-border bg-card/90 shadow-sm backdrop-blur"
    role="group"
    aria-label="Basemap"
  >
    <button
      v-for="basemap in BASEMAPS"
      :key="basemap.id"
      type="button"
      class="px-2.5 py-1.5 text-xs font-medium transition-colors"
      :class="basemap.id === active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
      :aria-pressed="basemap.id === active"
      @click="emit('select', basemap.id)"
    >
      {{ basemap.label }}
    </button>
  </div>
</template>
