import { Plugin } from "@opencode/plugin"
import { realpathSync } from "fs"
import path from "path"

// Whale-chan reacts to OpenCode sessions: she thinks while the agent works,
// cheers when a turn succeeds, gets angry when it fails, and hops when OpenCode
// is waiting on you (permission prompts and questions).
//
// Talks to the desktop mascot through the `whalechan` CLI, which exits quietly
// when she isn't running. Override the CLI path with WHALECHAN_BIN.

async function resolveCli(): Promise<string> {
	if (process.env.WHALECHAN_BIN) return process.env.WHALECHAN_BIN
	// This plugin lives at <repo>/integrations/opencode/whalechan and is usually
	// symlinked into ~/.config/opencode/plugins, so resolve the real directory.
	for (const dir of [import.meta.dir, safeRealpath(import.meta.dir)]) {
		const candidate = path.resolve(dir, "../../../desktop/whalechan")
		if (await Bun.file(candidate).exists()) return candidate
	}
	return "whalechan"
}

function safeRealpath(dir: string): string {
	try {
		return realpathSync(dir)
	} catch {
		return dir
	}
}

function clip(text: string, max = 60): string {
	const flat = text.replace(/\s+/g, " ").trim()
	return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat
}

export default Plugin.define({
	id: "whalechan",
	async setup(ctx) {
		const cli = await resolveCli()
		const controller = new AbortController()
		// sessionID -> is a top-level session (subagent sessions have a parentID)
		const topLevel = new Map<string, boolean>()

		const isTopLevel = async (sessionID: string): Promise<{ ok: boolean; title: string }> => {
			try {
				const session: any = await ctx.session.get({ sessionID })
				const ok = !session?.parentID
				topLevel.set(sessionID, ok)
				return { ok, title: session?.title ?? "" }
			} catch {
				return { ok: topLevel.get(sessionID) ?? true, title: "" }
			}
		}

		const react = (event: string, key: string, text = "", quiet = false) => {
			const args = [cli, "-q", "react", event, "--key", key]
			if (quiet) args.push("--quiet-line")
			if (text) args.push(text)
			try {
				Bun.spawn(args, { stdin: "ignore", stdout: "ignore", stderr: "ignore" })
			} catch {}
		}

		void (async () => {
			try {
				for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
					const data: any = (event as any).data ?? {}
					const sessionID: string | undefined = data.sessionID
					const key = `opencode:${event.type}:${sessionID ?? data.id ?? ""}`

					switch (event.type) {
						case "session.execution.started": {
							if (!sessionID || topLevel.get(sessionID) === false) break
							if (!(await isTopLevel(sessionID)).ok) break
							react("working", key, "", true)
							break
						}
						case "session.execution.succeeded":
						case "session.execution.failed": {
							if (!sessionID) break
							const { ok, title } = await isTopLevel(sessionID)
							if (!ok) break
							const name = clip(title)
							if (event.type === "session.execution.succeeded") {
								react("success", key, name ? `Done: ${name}` : "")
							} else {
								react("error", key, name ? `That went badly: ${name}` : "")
							}
							break
						}
						case "session.execution.interrupted": {
							if (sessionID && !(await isTopLevel(sessionID)).ok) break
							react("idle", key, "", true)
							break
						}
						case "permission.asked":
							react("attention", key, "OpenCode wants your permission.")
							break
						case "form.created":
							react("attention", key, "OpenCode has a question for you.")
							break
					}
				}
			} catch (error) {
				if (!controller.signal.aborted) console.error("whalechan plugin: event stream stopped", error)
			}
		})()

		return () => controller.abort()
	},
})
