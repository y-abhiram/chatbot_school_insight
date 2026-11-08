-- Non-destructive addition: let users query their own leave status, not only pending applications.
CREATE OR REPLACE VIEW insight.leave_requests WITH(security_barrier=true) AS
SELECT lr.leave_id,lt.type_name,lr.from_date,lr.to_date,lr.status,lr.admin_remarks,
 u.first_name||' '||coalesce(u.last_name,'') AS applicant
FROM school.leave_requests lr JOIN school.leave_types lt USING(leave_type_id)
JOIN school.users u ON u.user_id=lr.applicant_id WHERE insight.allowed_user(lr.applicant_id);
GRANT SELECT ON insight.leave_requests TO insight_query;
