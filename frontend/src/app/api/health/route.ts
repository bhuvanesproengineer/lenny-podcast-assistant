import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    service: 'lenny-frontend',
    timestamp: new Date().toISOString(),
  });
}
