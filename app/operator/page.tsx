import { auth } from "@/auth";
import OperatorView from "@/components/OperatorView";
import SessionBar from "@/components/SessionBar";
import ViewportSync from "@/components/ViewportSync";

export default async function OperatorPage() {
  const session = await auth();
  const user = session?.user;

  return (
    <div
      className="fd-page"
      style={{
        minHeight: "100vh",
        background: "var(--fd-bg)",
        color: "var(--fd-text)",
        padding: "74px 20px 40px",
        position: "relative",
      }}
    >
      <ViewportSync />
      <SessionBar name={user?.name ?? ""} />
      <OperatorView
        operatorName={user?.name ?? "Maria Chen"}
        operatorTitle={user?.title ?? "Director"}
      />
    </div>
  );
}
