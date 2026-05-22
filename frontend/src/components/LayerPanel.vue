<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { useJobStore } from '../stores/job'
import LayerCard from './LayerCard.vue'

const store = useJobStore()
const { layers } = storeToRefs(store)
</script>

<template>
  <div class="space-y-2">
    <h2 class="text-sm uppercase tracking-wide text-slate-400">
      Layers ({{ layers.length }})
    </h2>
    <p v-if="!layers.length" class="text-sm text-slate-500">No layers yet.</p>
    <LayerCard v-for="layer in layers" :key="layer.layer_id" :layer="layer" />
  </div>
</template>
