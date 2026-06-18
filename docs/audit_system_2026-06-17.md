# Audit complet de cohérence — 2026-06-17

## Synthèse

Cet audit repasse le dépôt complet avec l'angle demandé : vérifier que le système reste cohérent après les évolutions récentes et repérer les surcouches inutiles. Le périmètre couvre le backend FastAPI/Python, le frontend Vue/TypeScript, les contrats partagés, les scripts de déploiement et la documentation d'architecture.

Verdict : **l'architecture est globalement saine**. Les couches principales restent lisibles et justifiées : interface Vue, orchestration API, pipeline applicatif, domaine/contrats, conversion vers pivot SVG, génération G-code/EBB et pilotage matériel. Les contrôles automatiques lancés pendant l'audit sont verts (`ruff`, `eslint`, `vue-tsc`, `vite build`).

Le dépôt n'a pas besoin d'une réécriture. Les risques observés sont surtout des zones à surveiller : quelques fichiers très volumineux, une UI d'édition riche qui accumule beaucoup de composables, et des endpoints backend nombreux mais encore correctement séparés. Aucun doublon bloquant ni abstraction manifestement inutile n'a été identifié dans ce passage.

## Méthode et commandes exécutées

| Objectif | Commande | Résultat |
| --- | --- | --- |
| Inventaire des instructions locales | `find .. -name AGENTS.md -print` | Aucun `AGENTS.md` trouvé |
| Inventaire des fichiers applicatifs | `rg --files -g '!*node_modules*'` | Arborescence inspectée |
| Mesure du périmètre | script Python local sur `backend/pen_plotter` et `frontend/src` | 196 fichiers Python applicatifs, 329 fichiers TS/Vue applicatifs |
| Lint backend | `uv run ruff check pen_plotter tests` | OK |
| Lint frontend | `npm run lint` | OK |
| Build/typecheck frontend | `npm run build` | OK |

## Cartographie vérifiée

### Backend

Le backend suit une séparation nette :

- `api/` expose les routes HTTP/WebSocket et délègue la logique.
- `application/` regroupe les services de cas d'usage transverses : génération, préflight, bibliothèque de fichiers, cache IR.
- `domain/` porte les modèles métier et contrats.
- `converters/` normalise les formats d'entrée vers le pivot SVG.
- `core/` contient les primitives format-agnostiques : layers, toolpath, G-code, EBB, post-traitement, sécurité SVG.
- `hardware/` encapsule transport série, streaming et contrôleur matériel.
- `manifests/` et `domain/*/schemas` maintiennent la stratégie de contrats dynamiques.

Cette découpe reste alignée avec le document d'architecture existant : une seule représentation pivot SVG puis un pipeline unique pour l'extraction des layers, l'optimisation et la génération machine.

### Frontend

Le frontend est structuré autour de :

- `api/` pour le client HTTP/WebSocket typé.
- `application/` pour la pipeline impérative testable `optimize → preflight → generate`.
- `domain/` pour les types et validateurs proches des contrats backend.
- `stores/` pour l'état Pinia de l'application.
- `composables/` pour extraire la logique UI réutilisable.
- `components/` et `components/edit`/`components/v2` pour les écrans opérateur et éditeur.

La séparation est cohérente. La plus forte complexité se concentre dans l'éditeur, ce qui correspond au domaine fonctionnel plutôt qu'à une surcouche arbitraire.

## Points positifs

1. **Contrat architectural stable** : la décision "pivot SVG unique" évite une explosion de chemins par type de fichier.
2. **Contrats partagés maîtrisés** : OpenAPI et manifests limitent les duplications backend/frontend.
3. **Matériel isolé** : l'injection du transport rend le contrôleur testable sans plotter réel.
4. **Pipeline frontend extrait du store** : la génération est testable hors Pinia, donc moins couplée à l'UI.
5. **Qualité outillée** : les checks `ruff`, `eslint` et `vue-tsc` passent sur l'état courant.
6. **Documentation riche** : les ADR, guides de conversion, profils machine et audits antérieurs expliquent les contraintes structurantes.

## Zones de vigilance

### 1. Fichiers backend très volumineux

Les plus gros fichiers backend sont :

- `core/pdf_postprocess.py` : 2014 lignes.
- `typography/hershey.py` : 801 lignes.
- `core/gcode.py` : 701 lignes.
- `converters/bitmap/__init__.py` : 618 lignes.
- `api/files.py` : 601 lignes.

Ces fichiers ne sont pas forcément incohérents, mais ils deviennent coûteux à relire et à auditer. La priorité n'est pas d'ajouter une abstraction, mais de découper seulement si un sous-domaine clair apparaît : extraction de blocs PDF, helpers de géométrie, ou services de fichiers.

### 2. Fichiers frontend très volumineux

Les plus gros fichiers frontend sont :

- `domain/api-types.ts` : généré, donc acceptable.
- `data/printRegistry.ts` : catalogue volumineux, acceptable tant qu'il reste déclaratif.
- `stores/job.ts` : 2102 lignes, zone la plus sensible.
- `api/client.ts` : 1613 lignes.
- `composables/useBitmapDraft.ts` : 1492 lignes.
- `components/v2/EditModalV2.vue` : 1158 lignes.

La recommandation est de surveiller surtout `stores/job.ts` et `EditModalV2.vue`. Ils ne doivent pas redevenir des "god objects". Les extractions existantes dans `application/runGeneratePipeline.ts` et les composables vont dans le bon sens.

### 3. Surface API nombreuse

Le backend possède beaucoup de routers (`upload`, `preview`, `preview_stream`, `rerender`, `generate`, `preflight`, `plans`, `queue`, `plotter`, etc.). Ce n'est pas encore une incohérence : la granularité suit les cas d'usage. À surveiller toutefois : éviter de placer de la logique métier directement dans de nouveaux routers ; les nouveaux flux devraient passer par `application/` ou `core/`.

### 4. Dette UI volontaire

L'éditeur Vue a beaucoup de composables et de cartes spécialisées. C'est justifié par le nombre d'options métier, mais il faut garder une règle stricte :

- les composants rendent et émettent ;
- les composables portent les transitions d'état UI ;
- `application/` porte les workflows applicatifs ;
- `stores/` orchestre sans absorber toute la logique.

## Recommandations prioritaires

1. **Ne pas ajouter de nouvelle couche globale** : le modèle actuel est suffisamment découpé. Une couche supplémentaire "service" ou "manager" générique risquerait d'ajouter la surcouche que l'audit cherche à éviter.
2. **Extraire par domaine concret uniquement** : si un fichier dépasse encore en taille, extraire une fonction ou un module nommé d'après une responsabilité métier précise, pas d'après un pattern abstrait.
3. **Garder les routers minces** : toute nouvelle logique de génération, préflight, fichiers ou queue doit rejoindre `application/`/`core/`.
4. **Continuer à tester les contrats** : maintenir les snapshots OpenAPI/manifests et les tests de compatibilité est plus important qu'une duplication de types côté frontend.
5. **Faire un audit de dette UI ciblé avant la prochaine grosse évolution éditeur** : `stores/job.ts`, `useBitmapDraft.ts`, `EditModalV2.vue` et `api/client.ts` sont les meilleurs candidats.

## Conclusion

Le système a beaucoup avancé, mais il reste construit autour de responsabilités compréhensibles. L'audit ne justifie pas une refonte lourde. La meilleure trajectoire est une discipline de simplification continue : routers fins, workflows dans `application/`, logique pure dans `core`/`domain`, composants Vue focalisés sur le rendu, et extraction uniquement quand une responsabilité métier claire apparaît.
