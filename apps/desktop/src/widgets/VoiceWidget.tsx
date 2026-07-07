import { VoiceButton } from "../components/VoiceButton";

export function VoiceWidget() {
  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Voice</h2>
      <VoiceButton />
    </div>
  );
}
