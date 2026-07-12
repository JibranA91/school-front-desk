import { auth } from "@/auth";
import ParentView from "@/components/ParentView";
import SessionBar from "@/components/SessionBar";

export default async function Home() {
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
      <SessionBar name={user?.name ?? ""} />
      <ParentView />
    </div>
  );
}
