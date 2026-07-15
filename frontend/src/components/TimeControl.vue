<script setup lang="ts">
import { Pause, Play, RotateCcw } from "lucide-vue-next";
import { computed, onUnmounted, ref, watch } from "vue";

import { nextStep, roundToBucket } from "@/lib/timeControl";

const props = defineProps<{ modelValue: Date | null }>();
const emit = defineEmits<{ "update:modelValue": [time: Date | null] }>();

/** Animation cadence: one hour of alert time per tick. */
const STEP_MINUTES = 60;
const TICK_MS = 1200;

const playing = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;

const isLive = computed(() => props.modelValue === null);

/** datetime-local wants local time without zone; keep minutes precision. */
function toInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const inputValue = computed(() => toInputValue(props.modelValue ?? new Date()));

function onInput(event: Event) {
  const raw = (event.target as HTMLInputElement).value;
  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) emit("update:modelValue", roundToBucket(parsed));
}

function stop() {
  playing.value = false;
  clearInterval(timer);
}

function togglePlay() {
  if (playing.value) {
    stop();
    return;
  }
  playing.value = true;
  // animating from "live" starts 24h back so there is something to watch
  if (props.modelValue === null) {
    emit("update:modelValue", roundToBucket(nextStep(new Date(), -24 * 60)));
  }
  timer = setInterval(() => {
    const current = props.modelValue ?? new Date();
    const next = nextStep(current, STEP_MINUTES);
    if (next.getTime() >= Date.now()) {
      stop();
      emit("update:modelValue", null); // caught up — back to live
      return;
    }
    emit("update:modelValue", next);
  }, TICK_MS);
}

function backToLive() {
  stop();
  emit("update:modelValue", null);
}

watch(() => props.modelValue, (v) => {
  if (v === null) stop();
});

onUnmounted(stop);
</script>

<template>
  <div
    class="pointer-events-auto flex flex-col gap-1 rounded-lg border border-border bg-card/95 px-3 py-2 shadow-sm backdrop-blur"
    role="group"
    aria-label="Time control"
  >
    <!-- reserved slot for the alert-density histogram waveform (API pending) -->
    <div class="h-6 rounded-sm bg-muted/40" data-testid="waveform-slot" aria-hidden="true"></div>

    <div class="flex items-center gap-2">
      <button
        type="button"
        class="rounded-md border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        :title="playing ? 'Pause' : 'Play (1h per step)'"
        :aria-pressed="playing"
        data-testid="play-toggle"
        @click="togglePlay"
      >
        <Pause v-if="playing" class="size-4" aria-hidden="true" />
        <Play v-else class="size-4" aria-hidden="true" />
      </button>

      <input
        type="datetime-local"
        class="rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground"
        :value="inputValue"
        aria-label="View alerts at date and time"
        @change="onInput"
      />

      <button
        v-if="!isLive"
        type="button"
        class="flex items-center gap-1 rounded-md border border-border px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        title="Return to now"
        data-testid="back-to-live"
        @click="backToLive"
      >
        <RotateCcw class="size-3.5" aria-hidden="true" />
        Now
      </button>
      <span
        v-else
        class="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground"
        title="Showing currently active alerts"
      >
        Live
      </span>
    </div>
  </div>
</template>
