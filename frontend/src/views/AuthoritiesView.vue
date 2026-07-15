<script setup lang="ts">
import { ExternalLink, Landmark } from "lucide-vue-next";
import { onMounted, ref } from "vue";

import { type Authority, fetchAuthorities } from "@/lib/api";
import { countryFlagEmoji } from "@/lib/countryFlag";

const authorities = ref<Authority[]>([]);
const state = ref<"loading" | "ready" | "error">("loading");

onMounted(async () => {
  try {
    authorities.value = await fetchAuthorities();
    state.value = "ready";
  } catch {
    state.value = "error";
  }
});
</script>

<template>
  <section class="mx-auto flex h-full max-w-3xl flex-col gap-6 overflow-auto p-6 md:p-8">
    <header class="flex flex-col gap-1">
      <h1 class="flex items-center gap-2 text-xl font-semibold">
        <Landmark class="size-5 text-muted-foreground" aria-hidden="true" />
        Alerting authorities
      </h1>
      <p class="text-sm text-muted-foreground">
        National authorities whose CAP alerts this aggregator carries.
      </p>
    </header>

    <p v-if="state === 'loading'" class="text-sm text-muted-foreground">Loading authorities…</p>
    <p v-else-if="state === 'error'" class="text-sm text-destructive" role="alert">
      Could not load the authorities list. Please try again later.
    </p>
    <p v-else-if="!authorities.length" class="text-sm text-muted-foreground">
      No authorities are registered yet.
    </p>

    <ul v-else class="flex flex-col gap-3">
      <li
        v-for="authority in authorities"
        :key="authority.slug"
        class="flex items-center justify-between gap-4 rounded-lg border border-border bg-card p-4"
      >
        <div class="flex min-w-0 items-center gap-3">
          <span class="text-2xl" aria-hidden="true">{{ countryFlagEmoji(authority.country) }}</span>
          <div class="min-w-0">
            <p class="truncate font-medium">{{ authority.name }}</p>
            <p class="text-sm text-muted-foreground">{{ authority.country_name }}</p>
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-4">
          <span
            data-testid="alert-count"
            class="rounded-full border border-border bg-secondary px-2.5 py-0.5 text-xs font-medium text-secondary-foreground"
            :title="`${authority.active_alert_count} currently active alert(s)`"
          >
            {{ authority.active_alert_count }} active
          </span>
          <a
            v-if="authority.website"
            :href="authority.website"
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            Website
            <ExternalLink class="size-3.5" aria-hidden="true" />
          </a>
        </div>
      </li>
    </ul>
  </section>
</template>
