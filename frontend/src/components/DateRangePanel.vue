<script setup lang="ts">
import { ref } from "vue";

import { DATE_PRESETS, type DatePresetKey, type DateRange, matchPreset, presetRange } from "@/lib/dateRange";

/**
 * The Date range sidebar panel: one-click presets plus a Custom mode with
 * From/To pickers. Presets resolve to absolute dates (the URL stays a stable
 * snapshot); the checked radio is derived from the applied range on mount,
 * but Custom is sticky afterwards so hand-picked dates that happen to equal
 * a preset don't yank the pickers away mid-edit.
 */
const props = defineProps<{ modelValue: DateRange }>();
const emit = defineEmits<{ "update:modelValue": [range: DateRange] }>();

const selected = ref<DatePresetKey | "custom">(matchPreset(props.modelValue) ?? "custom");

function pick(key: DatePresetKey | "custom") {
  selected.value = key;
  if (key !== "custom") emit("update:modelValue", presetRange(key));
}

function setBound(bound: "from" | "to", event: Event) {
  emit("update:modelValue", { ...props.modelValue, [bound]: (event.target as HTMLInputElement).value });
}
</script>

<template>
  <section class="sidebar-panel" aria-label="Date range">
    <header class="sidebar-panel__header">
      <h3>Date range</h3>
    </header>
    <div class="flex flex-col gap-0.5 p-2">
      <label
        v-for="preset in [...DATE_PRESETS, { key: 'custom' as const, label: 'Custom' }]"
        :key="preset.key"
        class="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <input
          type="radio"
          name="date-range-preset"
          class="size-3.5 accent-primary"
          :value="preset.key"
          :checked="selected === preset.key"
          :data-testid="`range-preset-${preset.key}`"
          @change="pick(preset.key)"
        />
        {{ preset.label }}
      </label>

      <div v-if="selected === 'custom'" class="mt-1 flex flex-col gap-2 px-1.5 pb-1">
        <label class="flex flex-col text-xs text-muted-foreground">
          From
          <input
            type="date"
            class="mt-0.5 rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
            :value="modelValue.from"
            data-testid="range-from"
            @change="setBound('from', $event)"
          />
        </label>
        <label class="flex flex-col text-xs text-muted-foreground">
          To
          <input
            type="date"
            class="mt-0.5 rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground"
            :value="modelValue.to"
            data-testid="range-to"
            @change="setBound('to', $event)"
          />
        </label>
      </div>
    </div>
  </section>
</template>
