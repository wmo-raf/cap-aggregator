<script setup lang="ts">
import { Bell, Mail, Radio, Webhook } from "lucide-vue-next";

const channels = [
  {
    icon: Mail,
    title: "Email alerts",
    description:
      "Subscribe to email notifications for the countries, hazard types and severities you care about.",
  },
  {
    icon: Radio,
    title: "MQTT out-topics",
    description:
      "Machine-to-machine push: subscribe to the aggregator's MQTT broker and receive resolved CAP alerts in near real time.",
  },
  {
    icon: Webhook,
    title: "Webhooks",
    description:
      "Register an HTTPS endpoint and receive a signed delivery for every new, updated or cancelled alert matching your filters.",
  },
];
</script>

<template>
  <section class="mx-auto flex h-full max-w-2xl flex-col justify-center gap-8 p-8">
    <header class="flex flex-col items-center gap-3 text-center">
      <span
        class="inline-flex items-center gap-2 rounded-full border border-border bg-secondary px-3 py-1 text-xs font-medium text-secondary-foreground"
      >
        <Bell class="size-3.5" aria-hidden="true" />
        Coming soon
      </span>
      <h1 class="text-2xl font-semibold">Real-time alert notifications</h1>
      <p class="text-sm text-muted-foreground">
        CAP Aggregator will let you register once and receive emergency alerts from
        every connected authority, the moment they are published.
      </p>
    </header>

    <ul class="flex flex-col gap-4">
      <li
        v-for="channel in channels"
        :key="channel.title"
        class="flex items-start gap-4 rounded-lg border border-border bg-card p-4"
      >
        <component :is="channel.icon" class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div>
          <h2 class="text-sm font-semibold">{{ channel.title }}</h2>
          <p class="text-sm text-muted-foreground">{{ channel.description }}</p>
        </div>
      </li>
    </ul>

    <p class="text-center text-xs text-muted-foreground">
      These channels are planned and not yet available. No sign-up is collected at
      this stage — check back here as the service develops.
    </p>
  </section>
</template>
