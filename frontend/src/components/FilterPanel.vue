<script setup lang="ts">
import { ChevronDown } from "lucide-vue-next";
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
  { field: "severity" as const, label: "Severity", open: true, options: SEVERITIES.map((s) => ({ value: s.label, label: s.label })) },
  { field: "urgency" as const, label: "Urgency", open: false, options: URGENCIES.map((v) => ({ value: v, label: v })) },
  { field: "certainty" as const, label: "Certainty", open: false, options: CERTAINTIES.map((v) => ({ value: v, label: v })) },
  { field: "category" as const, label: "Category", open: false, options: CATEGORIES.map((v) => ({ value: v, label: v })) },
  { field: "msgType" as const, label: "Message type", open: false, options: MSG_TYPES.map((v) => ({ value: v, label: v })) },
  { field: "country" as const, label: "Country", open: false, options: props.countries.map((c) => ({ value: c.code.toLowerCase(), label: c.name })) },
]);

function toggle(field: keyof AlertFilters, value: string) {
  const current = props.modelValue[field];
  const next = current.includes(value) ? current.filter((v) => v !== value) : [...current, value];
  emit("update:modelValue", { ...props.modelValue, [field]: next });
}

const isActive = computed(() => hasActiveFilters(props.modelValue));
</script>

<template>
  <section class="sidebar-panel" aria-label="Filters">
    <header class="sidebar-panel__header">
      <h3>Filters</h3>
      <button
        v-if="isActive"
        type="button"
        data-testid="clear-filters"
        class="text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        @click="emit('update:modelValue', emptyFilters())"
      >
        Clear all
      </button>
    </header>

    <div class="flex flex-col gap-1.5 p-2">
      <details
        v-for="facet in facets"
        :key="facet.field"
        :open="facet.open"
        class="group rounded-md border border-border/70 bg-background/40"
      >
        <summary class="flex cursor-pointer items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-sm font-medium select-none [&::-webkit-details-marker]:hidden">
          <span class="flex items-center gap-2">
            {{ facet.label }}
            <span v-if="modelValue[facet.field].length" class="rounded-full bg-primary px-1.5 text-[10px] font-semibold text-primary-foreground">
              {{ modelValue[facet.field].length }}
            </span>
          </span>
          <ChevronDown class="size-4 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden="true" />
        </summary>
        <ul class="flex flex-col gap-0.5 px-2.5 pt-0.5 pb-2">
          <li v-for="option in facet.options" :key="option.value">
            <label class="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
              <input
                type="checkbox"
                class="size-3.5 accent-primary"
                :checked="modelValue[facet.field].includes(option.value)"
                @change="toggle(facet.field, option.value)"
              />
              {{ option.label }}
            </label>
          </li>
        </ul>
      </details>
    </div>
  </section>
</template>
