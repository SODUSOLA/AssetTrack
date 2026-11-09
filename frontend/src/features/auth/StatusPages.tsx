import { ButtonLink } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/Feedback";
import { PageHeader } from "@/components/ui/Layout";

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Page not found" />
      <EmptyState
        title="There is nothing at this address"
        description="The page may have moved, or the link may be wrong."
        action={
          <ButtonLink to="/" variant="primary">
            Go to the dashboard
          </ButtonLink>
        }
      />
    </>
  );
}

export function ForbiddenPage() {
  return (
    <>
      <PageHeader title="Not available to you" />
      <EmptyState
        title="Your role cannot open this page"
        description="If you think you should have access, ask the Head of Engineering."
        action={
          <ButtonLink to="/" variant="primary">
            Go to the dashboard
          </ButtonLink>
        }
      />
    </>
  );
}
