export const meta = {
  name: "nddev-builder",
  description: "Review target-owned NDDev MiMo Code setup artifacts before use.",
  whenToUse: "when checking NDDev-managed MiMo Code setup files inside the isolated target",
  phases: [{ title: "Inspect" }, { title: "Report" }],
  permissions: [{ permission: "read", patterns: ["**/*"], reason: "inspect managed setup files" }],
}

export default async function () {
  phase("Inspect")
  const files = await glob(".mimocode/**")
  const configExists = await exists("config/mimocode.json")
  phase("Report")
  return {
    configExists,
    managedWorkflowFiles: files,
  }
}
