<script setup lang="ts">
import { cn } from "@/lib/utils";
import { buttonVariants, type ButtonVariants } from ".";

const props = withDefaults(
  defineProps<{
    variant?: ButtonVariants["variant"];
    size?: ButtonVariants["size"];
    type?: "button" | "submit" | "reset";
  }>(),
  { variant: "default", size: "default", type: "button" },
);
</script>

<template>
  <button :type="props.type" :class="cn(buttonVariants({ variant: props.variant, size: props.size }), $attrs.class as string)">
    <slot />
  </button>
</template>
