import { auth } from "@/auth";
import OperatorView from "@/components/OperatorView";
import SessionBar from "@/components/SessionBar";

export default async function OperatorPage() {
  const session = await auth();
  const user = session?.user;

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#F7F9FB",
        color: "#18181D",
        padding: "74px 20px 40px",
        position: "relative",
      }}
    >
      <SessionBar name={user?.name ?? ""} role="operator" active="operator" />
      <OperatorView
        operatorName={user?.name ?? "Maria Chen"}
        operatorTitle={user?.title ?? "Director"}
      />
    </div>
  );
}
