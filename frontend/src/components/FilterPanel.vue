<script setup lang="ts">
import { computed } from "vue";

import { type AlertFilters, emptyFilters, hasActiveFilters } from "@/lib/filters";
import { SEVERITIES } from "@/lib/severity";
import { CATEGORIES, CERTAINTIES, MSG_TYPES, URGENCIES } from "@/lib/vocab";

const props = defineProps<{
  modelValue: AlertFilters;
  countries: { code: string; name: string }[];
}>();
const emit = defineEmits<{ "update:modelValue": [filters: AlertFilters] }>();

const facets = computed(() => [
  { field: "severity" as const, label: "Severity", options: SEVERITIES.map((s) => ({ value: s.label, label: s.label })) },
  { field: "urgency" as const, label: "Urgency", options: URGENCIES.map((v) => ({ value: v, label: v })) },
  { field: "certainty" as const, label: "Certainty", options: CERTAINTIES.map((v) => ({ value: v, label: v })) },
  { field: "category" as const, label: "Category", options: CATEGORIES.map((v) => ({ value: v, label: v })) },
  { field: "msgType" as const, label: "Message type", options: MSG_TYPES.map((v) => ({ value: v, label: v })) },
  { field: "country" as const, label: "Country", options: props.countries.map((c) => ({ value: c.code.toLowerCase(), label: c.name })) },
]);

function toggle(field: keyof AlertFilters, value: string) {
  const current = props.modelValue[field];
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  emit("update:modelValue", { ...props.modelValue, [field]: next });
}

function clearAll() {
  emit("update:modelValue", emptyFilters());
}

const isActive = computed(() => hasActiveFilters(props.modelValue));
</script>

<template>
  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between">
      <h3 class="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Filters</h3>
      <button
        v-if="isActive"
        type="button"
        data-testid="clear-filters"
        class="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        @click="clearAll"
      >
        Clear all
      </button>
    </div>

    <details v-for="facet in facets" :key="facet.field" class="group border-b border-border py-1 last:border-b-0">
      <summary class="flex cursor-pointer items-center justify-between py-1 text-sm select-none">
        {{ facet.label }}
        <span v-if="modelValue[facet.field].length" class="rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
          {{ modelValue[facet.field].length }}
        </span>
      </summary>
      <div class="flex flex-wrap gap-1.5 pt-1 pb-2">
        <button
          v-for="option in facet.options"
          :key="option.value"
          type="button"
          class="rounded-full border px-2 py-0.5 text-xs transition-colors"
          :class="modelValue[facet.field].includes(option.value)
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-border bg-background text-muted-foreground hover:bg-accent hover:text-accent-foreground'"
          :aria-pressed="modelValue[facet.field].includes(option.value)"
          @click="toggle(facet.field, option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </details>
  </div>
</template>
