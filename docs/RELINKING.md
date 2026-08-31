<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->

# Replacement and relinking

Every release contains a corresponding-source archive and per-target SDKs for
the ASS and FFmpeg scopes. Rebuild either scope with the documented target
command, preserving its public SONAME/framework names and ABI manifest. A
compatible ASS replacement receives a new `assRuntimeId`; an FFmpeg replacement
receives a new `runtimeId` bound to the selected ASS runtime.

On Android, replace the applicable `jni/<abi>/libkmediaffmpeg_*` files in the
ASS or FFmpeg AAR and rebuild/sign the application. On desktop, select an
application-controlled combined SDK directory with
`RuntimeSource.externalDirectory`; it must contain both manifests and the
required libraries. On Apple platforms, replace the applicable dynamic
XCFramework slices before the consuming application is signed.

The runtime never downloads executable code. Loading two different ASS or
FFmpeg runtime IDs in one process is rejected because native loaders cannot
safely unload and replace an already resolved graph.

The project-authored Java loader may be used under MIT when ahead-of-time
compiled into an application. That licensing choice removes any need to relink
the application merely to replace the loader, but does not change the LGPL
rights for the separate native libraries described above.
