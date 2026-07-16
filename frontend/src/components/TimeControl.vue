<script setup lang="ts">
import { Pause, Play } from "lucide-vue-next";
import { computed, onUnmounted, ref, watch } from "vue";

import { deriveTimeButtons, type TimeWindow } from "@/lib/timeButtons";
import { nextStep, roundToBucket } from "@/lib/timeControl";

/**
 * Two time modes over the single `t` state (null = live now):
 *  - Live: data-driven segmented chips (Now · +24h · weekday noons · Future)
 *    derived from the active + future alert windows, like the homepage map.
 *  - Historical: a past-capped datetime picker plus the replay animation.
 * The active tab is sticky local UI state, initialized from t (past t opens
 * Historical); switching tabs never changes t by itself.
 */
const props = defineProps<{ modelValue: Date | null; windows: TimeWindow[] }>();
const emit = defineEmits<{ "update:modelValue": [time: Date | null] }>();

const mode = ref<"live" | "historical">(
  props.modelValue !== null && props.modelValue.getTime() < Date.now() ? "historical" : "live",
);

// --- Live mode: segmented chips ---
const chips = computed(() => deriveTimeButtons(props.windows, new Date()));

const BUCKET_TOLERANCE_MS = 5 * 60 * 1000;

function isActiveChip(t: Date | null): boolean {
  if (t === null || props.modelValue === null) return t === props.modelValue;
  return Math.abs(t.getTime() - props.modelValue.getTime()) < BUCKET_TOLERANCE_MS;
}

function pickChip(t: Date | null) {
  stop();
  emit("update:modelValue", t && roundToBucket(t));
}

// --- Historical mode: past-capped picker + replay ---
/** Animation cadence: one hour of alert time per tick. */
const STEP_MINUTES = 60;
const TICK_MS = 1200;

const playing = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;

/** datetime-local wants local time without zone; keep minutes precision. */
function toInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const inputValue = computed(() => toInputValue(props.modelValue ?? new Date()));
const inputMax = computed(() => toInputValue(new Date()));

function onInput(event: Event) {
  const parsed = new Date((event.target as HTMLInputElement).value);
  if (Number.isNaN(parsed.getTime())) return;
  const capped = parsed.getTime() > Date.now() ? new Date() : parsed; // historical = past only
  emit("update:modelValue", roundToBucket(capped));
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
  if (props.modelValue === null || props.modelValue.getTime() >= Date.now()) {
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

function switchMode(next: "live" | "historical") {
  mode.value = next;
  if (next === "live") stop();
}

watch(
  () => props.modelValue,
  (value) => {
    if (value === null) {
      stop();
      mode.value = "live"; // e.g. the map's Reset button
    }
  },
);

onUnmounted(stop);
</script>

<template>
  <div
    class="pointer-events-auto flex flex-col gap-1.5 rounded-lg border border-border bg-card/95 px-3 py-2 shadow-sm backdrop-blur"
    role="group"
    aria-label="Time control"
  >
    <!-- reserved slot for the alert-density histogram waveform (API pending) -->
    <div class="h-6 rounded-sm bg-muted/40" data-testid="waveform-slot" aria-hidden="true"></div>

    <div class="flex flex-wrap items-center gap-2">
      <div class="flex divide-x divide-border overflow-hidden rounded-md border border-border" role="group" aria-label="Time mode">
        <button
          type="button"
          class="capagg-time-chip"
          :aria-pressed="mode === 'live'"
          data-testid="time-mode-live"
          @click="switchMode('live')"
        >
          Live
        </button>
        <button
          type="button"
          class="capagg-time-chip"
          :aria-pressed="mode === 'historical'"
          data-testid="time-mode-historical"
          @click="switchMode('historical')"
        >
          Historical
        </button>
      </div>

      <div v-if="mode === 'live'" class="flex divide-x divide-border overflow-hidden rounded-md border border-border">
        <button
          v-for="chip in chips"
          :key="chip.key"
          type="button"
          class="capagg-time-chip"
          :aria-pressed="isActiveChip(chip.t)"
          :data-time-button="chip.key"
          @click="pickChip(chip.t)"
        >
          {{ chip.label }}
        </button>
      </div>

      <template v-else>
        <button
          type="button"
          class="rounded-md border border-border p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          :title="playing ? 'Pause' : 'Replay the past 24h (1h per step)'"
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
          :max="inputMax"
          aria-label="View alerts at a past date and time"
          @change="onInput"
        />
      </template>
    </div>
  </div>
</template>
